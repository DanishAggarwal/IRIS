"""IRIS ingestion pipeline — orchestrates discovery → extraction → storage.

Run from the project root:
    python -m ingestion.pipeline

Design guarantees:
- Idempotent: re-running skips documents and pages already successfully processed.
- Resumable: a crash or quota exhaustion mid-run leaves successful pages
  untouched; only pending/failed pages are retried on the next run.
- Hash-aware: if a PDF's SHA-256 changes, it is treated as a new document.
- Original PDFs are never modified.
"""

import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

from database.connection import SessionLocal
from database.repository import (
    get_pending_pages,
    mark_document_complete,
    mark_document_failed,
    mark_page_failed,
    mark_page_success,
    upsert_document,
    upsert_page,
    get_document_by_hash,
)
from ingestion.discovery import compute_sha256, discover_pdfs
from ingestion.extractor import extract_digital_page, render_page_to_png_bytes
from ingestion.ocr import EXTRACTION_VERSION, extract_page
from ingestion.pdf_inspector import DocumentInspection, PageInspection, inspect_pdf

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

DOCUMENTS_DIR = Path(__file__).resolve().parent.parent / "documents"


def run_ingestion(source_dir: str | Path = DOCUMENTS_DIR) -> None:
    """Run the full ingestion pipeline over all PDFs in *source_dir*."""
    source_dir = Path(source_dir)
    logger.info("Starting IRIS ingestion from: %s", source_dir)

    discovered = discover_pdfs(source_dir)
    if not discovered:
        logger.warning("No PDFs found in %s. Nothing to do.", source_dir)
        return

    logger.info("Found %d PDF(s).", len(discovered))

    with SessionLocal() as session:
        for pdf_entry in discovered:
            _process_document(session, pdf_entry)

    logger.info("Ingestion complete.")


def _process_document(session, pdf_entry) -> None:
    """Ingest (or resume ingesting) a single PDF document."""
    pdf_path = Path(pdf_entry.path)
    logger.info("--- Processing: %s ---", pdf_path.name)

    sha256 = pdf_entry.sha256
    existing = get_document_by_hash(session, sha256)

    if existing and existing.status == "complete":
        logger.info(
            "  Skipping %s — already fully ingested (doc id %s).",
            pdf_path.name, existing.id,
        )
        return

    # Inspect PDF to get per-page classification
    logger.info("  Inspecting PDF structure...")
    inspection: DocumentInspection = inspect_pdf(pdf_entry)
    page_inspections: list[PageInspection] = inspection.pages
    page_count = inspection.total_pages
    overall_type = inspection.overall_type
    file_size = pdf_path.stat().st_size

    # Upsert document record
    doc = upsert_document(
        session,
        filename=pdf_path.name,
        sha256=sha256,
        file_size_bytes=file_size,
        page_count=page_count,
        source_path=str(pdf_path),
        overall_type=overall_type,
        status="extracting",
    )
    session.commit()
    logger.info(
        "  Document record: id=%s  pages=%d  type=%s", doc.id, page_count, overall_type
    )

    # Seed any pages not yet in DB as 'pending'
    for page_insp in page_inspections:
        upsert_page(session, document_id=doc.id, page_number=page_insp.page_number)
    session.commit()

    # Retrieve pages that still need work
    pending_db_pages = get_pending_pages(session, doc.id)
    logger.info(
        "  Pages to process: %d (skipping already-successful pages)",
        len(pending_db_pages),
    )

    if not pending_db_pages:
        mark_document_complete(session, doc.id)
        session.commit()
        return

    # Build a quick lookup: page_number → PageInspection
    page_insp_map: dict[int, PageInspection] = {
        p.page_number: p for p in page_inspections
    }

    any_failure = False
    for db_page in pending_db_pages:
        pnum = db_page.page_number
        page_insp = page_insp_map.get(pnum)
        cls = page_insp.classification if page_insp else "scanned"

        if cls in ("digital", "mixed"):
            _extract_digital(session, doc.id, pdf_path, pnum)
        else:
            _extract_ocr(session, doc.id, pdf_path, pnum)

        # Commit per page to guarantee durability and resumability on interruption
        session.commit()

        # Refresh to get the updated status
        session.refresh(db_page)
        if db_page.status == "failed":
            any_failure = True

    session.commit()

    if any_failure:
        logger.warning(
            "  %s: some pages failed — marking document as failed.", pdf_path.name
        )
        mark_document_failed(session, doc.id, "One or more pages failed extraction.")
    else:
        mark_document_complete(session, doc.id)
        logger.info("  %s: all pages extracted successfully.", pdf_path.name)
    session.commit()


def _extract_digital(session, document_id, pdf_path: Path, page_number: int) -> None:
    """Extract text from a digital/mixed page using PyMuPDF."""
    try:
        text = extract_digital_page(pdf_path, page_number)
        mark_page_success(
            session,
            document_id=document_id,
            page_number=page_number,
            extracted_text=text,
            extraction_method="digital",
            extraction_model=None,
            extraction_version=EXTRACTION_VERSION,
        )
        logger.debug(
            "  Page %d: digital extraction OK (%d chars)", page_number, len(text)
        )
    except Exception as exc:
        logger.error("  Page %d: digital extraction failed: %s", page_number, exc)
        mark_page_failed(
            session,
            document_id=document_id,
            page_number=page_number,
            error_message=str(exc),
            extraction_version=EXTRACTION_VERSION,
        )


def _extract_ocr(session, document_id, pdf_path: Path, page_number: int) -> None:
    """Render page to image and extract text via Gemini OCR."""
    try:
        image_bytes = render_page_to_png_bytes(pdf_path, page_number)
    except Exception as exc:
        logger.error("  Page %d: render failed: %s", page_number, exc)
        mark_page_failed(
            session,
            document_id=document_id,
            page_number=page_number,
            error_message=f"render error: {exc}",
            extraction_version=EXTRACTION_VERSION,
        )
        return

    result = extract_page(image_bytes, page_number)
    if result["status"] == "success":
        mark_page_success(
            session,
            document_id=document_id,
            page_number=page_number,
            extracted_text=result["text"],
            extraction_method="gemini_ocr",
            extraction_model=result["model_used"],
            extraction_version=EXTRACTION_VERSION,
        )
        logger.info(
            "  Page %d: OCR OK via %s (%d chars)",
            page_number,
            result["model_used"],
            len(result["text"]),
        )
    else:
        logger.error("  Page %d: OCR failed: %s", page_number, result["error"])
        mark_page_failed(
            session,
            document_id=document_id,
            page_number=page_number,
            error_message=result["error"] or "unknown OCR error",
            extraction_version=EXTRACTION_VERSION,
        )


if __name__ == "__main__":
    run_ingestion()
