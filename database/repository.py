"""Database access functions for IRIS ingestion pipeline.

All database interaction goes through these functions — application code
should not build raw queries. Functions are intentionally thin and
individually testable.
"""

import uuid
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert as pg_insert

from database.models import Document, Page, DocumentChunk


# ---------------------------------------------------------------------------
# Document helpers
# ---------------------------------------------------------------------------


def get_document_by_hash(session: Session, sha256: str) -> Optional[Document]:
    """Return the Document row matching *sha256*, or None if not found."""
    return session.query(Document).filter(Document.sha256 == sha256).first()


def upsert_document(session: Session, **kwargs) -> Document:
    """Insert a new Document or update it if the SHA-256 already exists.

    *kwargs* should include at minimum: filename, sha256.
    Optional: file_size_bytes, page_count, source_path, overall_type,
              metadata_, status, ocr_config_hash.

    Returns the persisted Document ORM object.
    """
    existing = get_document_by_hash(session, kwargs["sha256"])
    if existing:
        for key, value in kwargs.items():
            setattr(existing, key, value)
        session.flush()
        return existing

    doc = Document(**kwargs)
    session.add(doc)
    session.flush()
    return doc


def mark_document_complete(session: Session, document_id: uuid.UUID) -> None:
    doc = session.get(Document, document_id)
    if doc:
        doc.status = "complete"
        session.flush()


def mark_document_failed(session: Session, document_id: uuid.UUID, error: str) -> None:
    doc = session.get(Document, document_id)
    if doc:
        doc.status = "failed"
        session.flush()


# ---------------------------------------------------------------------------
# Page helpers
# ---------------------------------------------------------------------------


def get_page(
    session: Session, document_id: uuid.UUID, page_number: int
) -> Optional[Page]:
    """Return the Page row for (document_id, page_number), or None."""
    return (
        session.query(Page)
        .filter(Page.document_id == document_id, Page.page_number == page_number)
        .first()
    )


def upsert_page(session: Session, document_id: uuid.UUID, page_number: int, **kwargs) -> Page:
    """Insert a new Page or update it.  *kwargs* are Page column values."""
    existing = get_page(session, document_id, page_number)
    if existing:
        for key, value in kwargs.items():
            setattr(existing, key, value)
        session.flush()
        return existing

    page = Page(document_id=document_id, page_number=page_number, **kwargs)
    session.add(page)
    session.flush()
    return page


def get_pending_pages(session: Session, document_id: uuid.UUID) -> list[Page]:
    """Return all Page rows for a document that are not yet successfully extracted."""
    return (
        session.query(Page)
        .filter(Page.document_id == document_id, Page.status != "success")
        .order_by(Page.page_number)
        .all()
    )


def mark_page_success(
    session: Session,
    document_id: uuid.UUID,
    page_number: int,
    extracted_text: str,
    extraction_method: str,
    extraction_model: Optional[str],
    extraction_version: str,
    cleaned_text: Optional[str] = None,
    cleaning_version: Optional[str] = None,
) -> None:
    """Record a successful page extraction and optional cleaned text."""
    page = get_page(session, document_id, page_number)
    if page is None:
        page = Page(document_id=document_id, page_number=page_number)
        session.add(page)

    page.status = "success"
    page.extracted_text = extracted_text
    page.extraction_method = extraction_method
    page.extraction_model = extraction_model
    page.extraction_version = extraction_version
    if cleaned_text is not None:
        page.cleaned_text = cleaned_text
        page.cleaning_version = cleaning_version
    page.char_count = len(extracted_text) if extracted_text else 0
    page.error_message = None
    session.flush()


def mark_page_failed(
    session: Session,
    document_id: uuid.UUID,
    page_number: int,
    error_message: str,
    extraction_version: str,
) -> None:
    """Record a failed page extraction so it can be retried on next run."""
    page = get_page(session, document_id, page_number)
    if page is None:
        page = Page(document_id=document_id, page_number=page_number)
        session.add(page)

    page.status = "failed"
    page.error_message = error_message
    page.extraction_version = extraction_version
    session.flush()


def update_page_cleaned_text(
    session: Session,
    document_id: uuid.UUID,
    page_number: int,
    cleaned_text: str,
    cleaning_version: str,
) -> None:
    """Store cleaned text alongside raw extracted text without overwriting raw text."""
    page = get_page(session, document_id, page_number)
    if page:
        page.cleaned_text = cleaned_text
        page.cleaning_version = cleaning_version
        session.flush()


def get_pages_for_cleaning(
    session: Session, document_id: uuid.UUID, target_cleaning_version: Optional[str] = None
) -> list[Page]:
    """Return all successfully extracted pages for a document that need cleaning."""
    query = (
        session.query(Page)
        .filter(Page.document_id == document_id, Page.status == "success")
    )
    if target_cleaning_version:
        query = query.filter(
            (Page.cleaning_version != target_cleaning_version)
            | (Page.cleaning_version.is_(None))
        )
    return query.order_by(Page.page_number).all()


def update_document_metadata(
    session: Session, document_id: uuid.UUID, metadata_dict: dict
) -> None:
    """Merge or set metadata dict on the document record."""
    doc = session.get(Document, document_id)
    if doc:
        current_meta = dict(doc.metadata_ or {})
        current_meta.update(metadata_dict)
        doc.metadata_ = current_meta
        session.flush()


def get_all_documents(session: Session) -> list[Document]:
    """Return all Document rows ordered by filename."""
    return session.query(Document).order_by(Document.filename).all()



# ---------------------------------------------------------------------------
# Chunk helpers
# ---------------------------------------------------------------------------


def replace_document_chunks(
    session: Session,
    document_id: uuid.UUID,
    chunking_version: str,
    chunks_data: list[dict],
) -> list[DocumentChunk]:
    """Atomically replace all chunks for a document and chunking version.

    Args:
        session:          SQLAlchemy session.
        document_id:      UUID of document.
        chunking_version: e.g. 'chunk-v1'.
        chunks_data:      List of dicts with keys: chunk_index, chunk_text,
                          start_page, end_page, char_count, token_count,
                          section_title, metadata.

    Returns:
        List of persisted DocumentChunk instances.
    """
    # Delete existing chunks for this version
    session.query(DocumentChunk).filter(
        DocumentChunk.document_id == document_id,
        DocumentChunk.chunking_version == chunking_version,
    ).delete(synchronize_session=False)
    session.flush()

    new_chunks = []
    for cd in chunks_data:
        chunk = DocumentChunk(
            document_id=document_id,
            chunk_index=cd["chunk_index"],
            chunk_text=cd["chunk_text"],
            start_page=cd["start_page"],
            end_page=cd["end_page"],
            char_count=cd.get("char_count", len(cd["chunk_text"])),
            token_count=cd["token_count"],
            section_title=cd.get("section_title"),
            metadata_=cd.get("metadata"),
            chunking_version=chunking_version,
        )
        session.add(chunk)
        new_chunks.append(chunk)

    session.flush()
    return new_chunks


def get_chunks_for_document(
    session: Session,
    document_id: uuid.UUID,
    chunking_version: Optional[str] = None,
) -> list[DocumentChunk]:
    """Retrieve all chunks for a document, ordered by chunk_index."""
    query = session.query(DocumentChunk).filter(DocumentChunk.document_id == document_id)
    if chunking_version:
        query = query.filter(DocumentChunk.chunking_version == chunking_version)
    return query.order_by(DocumentChunk.chunk_index).all()


def count_chunks_for_document(
    session: Session,
    document_id: uuid.UUID,
    chunking_version: Optional[str] = None,
) -> int:
    """Return the total number of chunks for a document."""
    query = session.query(DocumentChunk).filter(DocumentChunk.document_id == document_id)
    if chunking_version:
        query = query.filter(DocumentChunk.chunking_version == chunking_version)
    return query.count()
