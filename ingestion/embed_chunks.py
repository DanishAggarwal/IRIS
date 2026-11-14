"""Incremental CLI Embedding Pipeline for IRIS Document Chunks.

Generates and persists 768-dimensional Gemini embeddings for chunks
stored in PostgreSQL using the M5 database foundation.

Usage:
    # Check embedding status:
    python -m ingestion.embed_chunks --status

    # Run 10-chunk pilot:
    python -m ingestion.embed_chunks --pilot

    # Incremental run (skips already embedded chunks by default):
    python -m ingestion.embed_chunks --batch-size 10

    # Limit to N chunks:
    python -m ingestion.embed_chunks --limit 10
"""

import argparse
import logging
import sys
import time
import uuid
from typing import Optional

from dotenv import load_dotenv

from database.connection import SessionLocal
from database.models import Document, DocumentChunk
from database.repository import (
    get_chunk_by_id,
    get_chunk_embedding_status,
    get_unembedded_chunks,
    store_chunk_embeddings_batch,
    DEFAULT_EMBEDDING_DIM,
)
from ingestion.embedding_provider import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_MODEL,
    embed_documents,
    get_embedding_config,
)

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# Canonical 10 representative chunks selected for Milestone 6 Pilot:
# 3 Digital Syllabus (narrative, 4-page span, orphan heading+body)
# 3 Handout Ver 1.0 (scanned multi-page narrative, multi-page table, single-page table)
# 4 Handout Ver 2.0 (15-col CO-PO matrix, 2-page consultation table, 3-page overview, evaluation table)
PILOT_CHUNK_IDS = [
    uuid.UUID("be3ae4f9-428a-4f7d-b327-1a745936a773"),  # CSE Syllabus #7 (Digital Narrative, p.13)
    uuid.UUID("d339d257-9874-47ca-b2ea-dc832ce59623"),  # CSE Syllabus #0 (Digital Multi-page, p.1-4)
    uuid.UUID("bb33a0fd-9977-4c8f-8ed6-116badd1f5aa"),  # CSE Syllabus #33 (Heading+Body, p.39)
    uuid.UUID("793d0971-ce4c-4b06-a730-e167fe995d67"),  # Ver 1.0 #16 (Scanned Multi-page Narrative, p.17-18)
    uuid.UUID("41882028-d964-4e30-b275-cdc3f878796e"),  # Ver 1.0 #0 (Scanned Multi-page Table, p.1-2)
    uuid.UUID("e4f09647-c93f-4fa2-82d6-14875e3a9991"),  # Ver 1.0 #1 (Scanned Single-page Table, p.2)
    uuid.UUID("e104fd5a-38c0-4fa8-abb0-8803f8c697d4"),  # Ver 2.0 #4 (Scanned 15-col CO-PO Matrix, p.4)
    uuid.UUID("2dd7beff-623c-4e6c-87eb-5e318a3ad1e1"),  # Ver 2.0 #5 (Scanned Consultation Table Multi-page, p.4-5)
    uuid.UUID("6f46370d-90a4-45c2-aa91-83fd48c41c23"),  # Ver 2.0 #1 (Scanned Multi-page Structured, p.1-3)
    uuid.UUID("d458d0e9-08c3-42b4-adf0-998e3365214e"),  # Ver 2.0 #8 (Scanned Evaluation Table, p.7)
]


def run_embedding_pipeline(
    pilot: bool = False,
    re_embed: bool = False,
    limit: Optional[int] = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    document_id: Optional[uuid.UUID] = None,
) -> dict:
    """Execute the incremental embedding pipeline.

    Returns summary dictionary with counts of embedded, skipped, failed chunks.
    """
    model_name, dimension = get_embedding_config()
    logger.info("Initializing embedding pipeline (model: %s, dim: %d)...", model_name, dimension)

    with SessionLocal() as session:
        initial_status = get_chunk_embedding_status(session, document_id=document_id)
        logger.info("Current embedding status: %s", initial_status)

        # 1. Identify chunks to process
        if pilot:
            logger.info("Pilot mode activated: targeting 10 representative chunks.")
            target_chunks = [c for cid in PILOT_CHUNK_IDS if (c := get_chunk_by_id(session, cid)) is not None]
            total_targeted = len(target_chunks)
            chunks_to_embed = [c for c in target_chunks if (re_embed or c.embedding is None)]
            skipped_count = total_targeted - len(chunks_to_embed)
        elif re_embed:
            logger.info("Re-embed mode: fetching all chunks matching filters.")
            query = session.query(DocumentChunk)
            if document_id:
                query = query.filter(DocumentChunk.document_id == document_id)
            query = query.order_by(DocumentChunk.document_id, DocumentChunk.chunk_index)
            if limit:
                query = query.limit(limit)
            chunks_to_embed = query.all()
            total_targeted = len(chunks_to_embed)
            skipped_count = 0
        else:
            logger.info("Incremental mode: fetching unembedded chunks (embedding IS NULL).")
            base_q = session.query(DocumentChunk)
            if document_id:
                base_q = base_q.filter(DocumentChunk.document_id == document_id)
            total_targeted = base_q.count()
            already_embedded = base_q.filter(DocumentChunk.embedding.isnot(None)).count()
            skipped_count = already_embedded

            chunks_to_embed = get_unembedded_chunks(
                session=session,
                document_id=document_id,
                limit=limit,
            )

        if not chunks_to_embed:
            logger.info("No chunks need embedding. Skipped: %d.", skipped_count)
            return {
                "total_targeted": total_targeted,
                "embedded": 0,
                "skipped": skipped_count,
                "failed": 0,
                "status": initial_status,
            }

        logger.info(
            "Ready to embed %d chunks (skipped %d already embedded) in batches of %d.",
            len(chunks_to_embed),
            skipped_count,
            batch_size,
        )

        embedded_count = 0
        failed_count = 0
        failed_chunk_ids = []

        # Process in batches
        for batch_start in range(0, len(chunks_to_embed), batch_size):
            batch = chunks_to_embed[batch_start : batch_start + batch_size]
            batch_texts = [c.chunk_text for c in batch]
            batch_ids = [c.id for c in batch]

            logger.info(
                "Processing batch %d-%d of %d chunks...",
                batch_start + 1,
                batch_start + len(batch),
                len(chunks_to_embed),
            )

            try:
                embeddings = embed_documents(texts=batch_texts, batch_size=len(batch_texts))
                if len(embeddings) != len(batch):
                    raise ValueError(
                        f"Expected {len(batch)} embeddings, but received {len(embeddings)}"
                    )

                updates = []
                for chunk, vec in zip(batch, embeddings):
                    updates.append(
                        {
                            "chunk_id": chunk.id,
                            "embedding": vec,
                            "embedding_model": model_name,
                            "embedding_dim": dimension,
                        }
                    )

                store_chunk_embeddings_batch(session=session, updates=updates, expected_dim=dimension)
                session.commit()
                embedded_count += len(batch)
                logger.info("Batch persisted successfully (%d/%d embedded).", embedded_count, len(chunks_to_embed))
                time.sleep(1.0)

            except Exception as exc:
                session.rollback()
                failed_count += len(batch)
                failed_chunk_ids.extend([str(cid) for cid in batch_ids])
                logger.error("Failed to embed batch %s: %s", [str(cid) for cid in batch_ids], exc)

        final_status = get_chunk_embedding_status(session, document_id=document_id)
        logger.info("Embedding pipeline completed.")
        logger.info("Results: embedded=%d, skipped=%d, failed=%d", embedded_count, skipped_count, failed_count)
        logger.info("Final embedding status: %s", final_status)

        return {
            "total_targeted": total_targeted,
            "embedded": embedded_count,
            "skipped": skipped_count,
            "failed": failed_count,
            "failed_chunk_ids": failed_chunk_ids,
            "status": final_status,
        }


def main():
    parser = argparse.ArgumentParser(description="IRIS Incremental Embedding Pipeline")
    parser.add_argument("--status", action="store_true", help="Print embedding status and exit")
    parser.add_argument("--pilot", action="store_true", help="Run 10-chunk pilot only")
    parser.add_argument("--re-embed", action="store_true", help="Force re-embedding of chunks")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of chunks to process")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help="Batch size for API calls")
    parser.add_argument("--doc-id", type=str, default=None, help="Filter by document UUID")

    args = parser.parse_args()

    doc_uuid = uuid.UUID(args.doc_id) if args.doc_id else None

    if args.status:
        with SessionLocal() as session:
            status = get_chunk_embedding_status(session, document_id=doc_uuid)
            print("Embedding Status:", status)
        sys.exit(0)

    results = run_embedding_pipeline(
        pilot=args.pilot,
        re_embed=args.re_embed,
        limit=args.limit,
        batch_size=args.batch_size,
        document_id=doc_uuid,
    )
    print("\nPipeline Summary:", results)


if __name__ == "__main__":
    main()
