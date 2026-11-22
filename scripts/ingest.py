"""IRIS Unified Ingestion & Preprocessing Pipeline Runner.

Runs the complete document processing pipeline end-to-end:
  1. PDF Discovery, Extraction (Digital / OCR) & Text Cleaning  (ingestion.pipeline)
  2. Institutional Metadata Classification & Audit Tagging     (ingestion.clean_corpus)
  3. Structure-Aware Semantic Chunking                          (ingestion.chunk_corpus)
  4. Incremental Vector Embedding Generation (pgvector)         (ingestion.embed_chunks)

Guarantees:
  - Idempotent: Automatically skips PDFs and chunks that have already been processed.
  - Resumable: Safely resumes from where it left off if interrupted or rate-limited.
  - Non-destructive: Original PDFs in documents/ are never modified.

Usage:
  # Run full pipeline incrementally (recommended):
  python scripts/ingest.py

  # Or using module syntax:
  python -m scripts.ingest

  # Check status without running ingestion:
  python scripts/ingest.py --status

  # Extract, clean, and chunk without generating embeddings:
  python scripts/ingest.py --skip-embeddings

  # Force complete re-processing of all documents and chunks:
  python scripts/ingest.py --force
"""

import argparse
import logging
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv()

from database.connection import SessionLocal
from database.models import Document, DocumentChunk, Page
from database.repository import get_chunk_embedding_status
from ingestion.chunk_corpus import run_chunk_corpus
from ingestion.clean_corpus import run_clean_corpus
from ingestion.discovery import compute_sha256, discover_pdfs
from ingestion.embed_chunks import run_embedding_pipeline
from ingestion.pipeline import DOCUMENTS_DIR, run_ingestion

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("iris.ingest")


def print_banner(title: str) -> None:
    """Print a clean visual section banner."""
    width = 75
    print("\n" + "=" * width)
    print(f" {title.upper()}")
    print("=" * width)


def get_corpus_summary() -> dict:
    """Query database and documents/ folder to compute current corpus state."""
    discovered = discover_pdfs(DOCUMENTS_DIR)
    discovered_by_hash = {p.sha256: p for p in discovered}

    with SessionLocal() as session:
        docs = session.query(Document).order_by(Document.created_at).all()
        doc_hashes = {d.sha256 for d in docs}

        total_pages = session.query(Page).count()
        success_pages = session.query(Page).filter(Page.status == "success").count()
        failed_pages = session.query(Page).filter(Page.status == "failed").count()
        pending_pages = session.query(Page).filter(Page.status == "pending").count()

        total_chunks = session.query(DocumentChunk).count()
        embedded_chunks = (
            session.query(DocumentChunk)
            .filter(DocumentChunk.embedding.isnot(None))
            .count()
        )
        unembedded_chunks = total_chunks - embedded_chunks

        unregistered_pdfs = [
            p.filename for h, p in discovered_by_hash.items() if h not in doc_hashes
        ]

        doc_details = []
        for d in docs:
            c_count = (
                session.query(DocumentChunk)
                .filter(DocumentChunk.document_id == d.id)
                .count()
            )
            emb_count = (
                session.query(DocumentChunk)
                .filter(
                    DocumentChunk.document_id == d.id,
                    DocumentChunk.embedding.isnot(None),
                )
                .count()
            )
            doc_details.append({
                "filename": d.filename,
                "status": d.status,
                "pages": d.page_count,
                "type": d.overall_type,
                "chunks": c_count,
                "embedded": emb_count,
            })

    return {
        "discovered_pdfs_count": len(discovered),
        "unregistered_pdfs": unregistered_pdfs,
        "documents": doc_details,
        "total_documents": len(docs),
        "total_pages": total_pages,
        "success_pages": success_pages,
        "failed_pages": failed_pages,
        "pending_pages": pending_pages,
        "total_chunks": total_chunks,
        "embedded_chunks": embedded_chunks,
        "unembedded_chunks": unembedded_chunks,
    }


def show_status() -> None:
    """Print formatted summary of the current IRIS corpus."""
    print_banner("IRIS Corpus & RAG Readiness Status")
    summary = get_corpus_summary()

    print(f"Directory: {DOCUMENTS_DIR}")
    print(f"Total PDFs found on disk: {summary['discovered_pdfs_count']}")

    if summary["unregistered_pdfs"]:
        print("\nNew PDFs detected (not yet in database):")
        for fn in summary["unregistered_pdfs"]:
            print(f"  + [NEW] {fn}")
    else:
        print("\nAll PDFs in documents/ are registered in the database.")

    print("\nDocument Registry in PostgreSQL:")
    print(f"{'Filename':<45} {'Pages':<7} {'Type':<10} {'Status':<10} {'Chunks':<8} {'Embedded':<8}")
    print("-" * 92)
    for d in summary["documents"]:
        emb_str = f"{d['embedded']}/{d['chunks']}"
        print(f"{d['filename'][:44]:<45} {d['pages']:<7} {d['type']:<10} {d['status']:<10} {d['chunks']:<8} {emb_str:<8}")

    print("-" * 92)
    print(f"Total Documents:  {summary['total_documents']}")
    print(f"Total Pages:      {summary['total_pages']} (Success: {summary['success_pages']}, Failed: {summary['failed_pages']}, Pending: {summary['pending_pages']})")
    print(f"Total Chunks:     {summary['total_chunks']} (Embedded: {summary['embedded_chunks']}, Unembedded: {summary['unembedded_chunks']})")

    if summary["total_chunks"] > 0 and summary["unembedded_chunks"] == 0 and not summary["unregistered_pdfs"]:
        print("\n[OK] RAG Engine is READY. All documents are chunked and 100% embedded.")
    else:
        pending_work = []
        if summary["unregistered_pdfs"]:
            pending_work.append(f"{len(summary['unregistered_pdfs'])} new PDF(s) to extract")
        if summary["pending_pages"] > 0:
            pending_work.append(f"{summary['pending_pages']} page(s) pending extraction")
        if summary["unembedded_chunks"] > 0:
            pending_work.append(f"{summary['unembedded_chunks']} chunk(s) awaiting vector embeddings")
        print(f"\n[ACTION NEEDED] Corpus needs update: {', '.join(pending_work)}.")
        print("Run 'python scripts/ingest.py' to process them.")


def run_full_pipeline(
    force: bool = False,
    skip_embeddings: bool = False,
    batch_size: int = 10,
) -> int:
    """Execute all pipeline steps sequentially."""
    start_time = time.time()
    print_banner("IRIS End-to-End Ingestion Pipeline")
    print(f"Starting at: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Settings: force={force}, skip_embeddings={skip_embeddings}, batch_size={batch_size}")

    # --- STEP 1: Ingestion & Extraction ---
    print_banner("Step 1/4: PDF Discovery, Page Extraction & Text Cleaning")
    try:
        run_ingestion()
    except Exception as exc:
        logger.error("Step 1 failed: %s", exc, exc_info=True)
        print(f"\n[ERROR] Ingestion failed: {exc}", file=sys.stderr)
        return 1

    # --- STEP 2: Metadata Classification ---
    print_banner("Step 2/4: Institutional Metadata Classification")
    try:
        run_clean_corpus()
    except Exception as exc:
        logger.error("Step 2 failed: %s", exc, exc_info=True)
        print(f"\n[ERROR] Metadata classification failed: {exc}", file=sys.stderr)
        return 2

    # --- STEP 3: Structure-Aware Chunking ---
    print_banner("Step 3/4: Structure-Aware Semantic Chunking")
    try:
        run_chunk_corpus(rechunk=force)
    except Exception as exc:
        logger.error("Step 3 failed: %s", exc, exc_info=True)
        print(f"\n[ERROR] Chunking failed: {exc}", file=sys.stderr)
        return 3

    # --- STEP 4: Vector Embeddings ---
    if skip_embeddings:
        print_banner("Step 4/4: Vector Embeddings (SKIPPED via --skip-embeddings)")
    else:
        print_banner("Step 4/4: Incremental Vector Embeddings (Gemini)")
        try:
            run_embedding_pipeline(
                re_embed=force,
                batch_size=batch_size,
            )
        except Exception as exc:
            logger.error("Step 4 failed: %s", exc, exc_info=True)
            print(f"\n[ERROR] Embedding generation failed: {exc}", file=sys.stderr)
            return 4

    elapsed = round(time.time() - start_time, 1)
    print_banner("Pipeline Execution Complete")
    print(f"Finished in {elapsed}s.")
    show_status()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="IRIS Unified Ingestion and Preprocessing Pipeline Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  python scripts/ingest.py                 # Incrementally process new documents and embed them
  python scripts/ingest.py --status        # View current corpus and embedding counts
  python scripts/ingest.py --skip-embeddings # Ingest and chunk without calling embedding API
  python scripts/ingest.py --force         # Re-chunk and re-embed all documents
""",
    )
    parser.add_argument(
        "--status",
        "-s",
        action="store_true",
        help="Display current corpus ingestion and embedding status without running pipeline.",
    )
    parser.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="Force re-chunking and re-embedding of all documents.",
    )
    parser.add_argument(
        "--skip-embeddings",
        action="store_true",
        help="Extract, clean, and chunk documents, but skip vector embedding generation.",
    )
    parser.add_argument(
        "--batch-size",
        "-b",
        type=int,
        default=10,
        help="Number of chunks per Gemini embedding API request (default: 10).",
    )

    args = parser.parse_args()

    if args.status:
        show_status()
        return 0

    return run_full_pipeline(
        force=args.force,
        skip_embeddings=args.skip_embeddings,
        batch_size=args.batch_size,
    )


if __name__ == "__main__":
    sys.exit(main())
