"""Database access functions for IRIS ingestion pipeline.

All database interaction goes through these functions — application code
should not build raw queries. Functions are intentionally thin and
individually testable.
"""

import math
import uuid
from typing import Optional, Sequence, Any

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


# ---------------------------------------------------------------------------
# Embedding helpers
# ---------------------------------------------------------------------------

DEFAULT_EMBEDDING_DIM = 768


def validate_embedding(
    embedding: Any, expected_dim: int = DEFAULT_EMBEDDING_DIM
) -> list[float]:
    """Validate that an embedding vector is finite, numeric, and matches expected dimensions.

    Args:
        embedding: Sequence of numeric values.
        expected_dim: Target dimension size (default: 768).

    Returns:
        List of float values.

    Raises:
        ValueError: If vector is not a sequence, wrong dimension, or contains NaN/Inf.
    """
    if embedding is None:
        raise ValueError("Embedding vector cannot be None")

    if isinstance(embedding, (str, bytes, dict)):
        raise ValueError("Embedding vector must be a sequence of numeric floats, not str/bytes/dict")

    try:
        vec = [float(x) for x in embedding]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Embedding vector contains non-numeric values: {exc}") from exc

    if len(vec) != expected_dim:
        raise ValueError(
            f"Embedding dimension mismatch: expected {expected_dim}, got {len(vec)}"
        )

    for i, val in enumerate(vec):
        if math.isnan(val) or math.isinf(val):
            raise ValueError(
                f"Embedding vector contains non-finite value ({val}) at index {i}"
            )

    return vec


def get_chunk_by_id(session: Session, chunk_id: uuid.UUID) -> Optional[DocumentChunk]:
    """Retrieve a single DocumentChunk by UUID."""
    return session.get(DocumentChunk, chunk_id)


def store_chunk_embedding(
    session: Session,
    chunk_id: uuid.UUID,
    embedding: Sequence[float],
    embedding_model: str,
    embedding_dim: int = DEFAULT_EMBEDDING_DIM,
) -> DocumentChunk:
    """Store or update an embedding vector and model metadata for an existing chunk.

    Strictly preserves chunk_text, page provenance (start_page, end_page, page_spans),
    section_title, and chunking_version.

    Args:
        session: SQLAlchemy session.
        chunk_id: UUID of DocumentChunk.
        embedding: Sequence of numeric floats.
        embedding_model: Identifier of the embedding model (e.g. 'text-embedding-004').
        embedding_dim: Dimension of vector (must match configured column, default: 768).

    Returns:
        Updated DocumentChunk instance.

    Raises:
        ValueError: If vector is invalid, dimensions mismatch, model string is empty,
                    or chunk does not exist.
    """
    if not embedding_model or not isinstance(embedding_model, str) or not embedding_model.strip():
        raise ValueError("embedding_model must be a non-empty string")

    clean_vec = validate_embedding(embedding, expected_dim=embedding_dim)

    chunk = get_chunk_by_id(session, chunk_id)
    if chunk is None:
        raise ValueError(f"DocumentChunk with ID {chunk_id} not found")

    chunk.embedding = clean_vec
    chunk.embedding_model = embedding_model.strip()
    chunk.embedding_dim = embedding_dim
    session.flush()
    return chunk


def store_chunk_embeddings_batch(
    session: Session,
    updates: list[dict],
    expected_dim: int = DEFAULT_EMBEDDING_DIM,
) -> int:
    """Transactionally persist embeddings for multiple chunks.

    Pre-validates all records before applying updates to ensure all-or-nothing atomicity.

    Args:
        session: SQLAlchemy session.
        updates: List of dicts, each with keys:
                 - chunk_id (uuid.UUID)
                 - embedding (Sequence[float])
                 - embedding_model (str)
                 - optional embedding_dim (int, defaults to expected_dim)
        expected_dim: Expected vector dimension.

    Returns:
        Number of updated chunks.

    Raises:
        ValueError: If any record has invalid vector, wrong dimension, missing chunk, etc.
    """
    if not updates:
        return 0

    validated_updates = []
    for idx, item in enumerate(updates):
        chunk_id = item.get("chunk_id")
        if not chunk_id:
            raise ValueError(f"Batch item at index {idx} missing 'chunk_id'")

        model = item.get("embedding_model")
        if not model or not isinstance(model, str) or not model.strip():
            raise ValueError(f"Batch item at index {idx} missing or invalid 'embedding_model'")

        dim = item.get("embedding_dim", expected_dim)
        vec = validate_embedding(item.get("embedding"), expected_dim=dim)

        chunk = get_chunk_by_id(session, chunk_id)
        if chunk is None:
            raise ValueError(f"Batch item at index {idx}: chunk {chunk_id} not found")

        validated_updates.append((chunk, vec, model.strip(), dim))

    for chunk, vec, model, dim in validated_updates:
        chunk.embedding = vec
        chunk.embedding_model = model
        chunk.embedding_dim = dim

    session.flush()
    return len(validated_updates)


def get_unembedded_chunks(
    session: Session,
    document_id: Optional[uuid.UUID] = None,
    chunking_version: Optional[str] = None,
    limit: Optional[int] = None,
) -> list[DocumentChunk]:
    """Retrieve chunks where embedding is NULL (pending embedding generation).

    Args:
        session: SQLAlchemy session.
        document_id: Optional UUID filter for a specific document.
        chunking_version: Optional version string filter.
        limit: Optional maximum number of chunks to return.

    Returns:
        List of DocumentChunk instances ordered by document_id and chunk_index.
    """
    query = session.query(DocumentChunk).filter(DocumentChunk.embedding.is_(None))
    if document_id is not None:
        query = query.filter(DocumentChunk.document_id == document_id)
    if chunking_version is not None:
        query = query.filter(DocumentChunk.chunking_version == chunking_version)

    query = query.order_by(DocumentChunk.document_id, DocumentChunk.chunk_index)
    if limit is not None:
        query = query.limit(limit)
    return query.all()


def get_chunk_embedding_status(
    session: Session,
    document_id: Optional[uuid.UUID] = None,
    chunking_version: Optional[str] = None,
) -> dict[str, int]:
    """Return embedding summary status counts for a document or entire corpus.

    Args:
        session: SQLAlchemy session.
        document_id: Optional UUID filter.
        chunking_version: Optional version string filter.

    Returns:
        Dict with keys: 'total_chunks', 'embedded_chunks', 'unembedded_chunks'.
    """
    base_query = session.query(DocumentChunk)
    if document_id is not None:
        base_query = base_query.filter(DocumentChunk.document_id == document_id)
    if chunking_version is not None:
        base_query = base_query.filter(DocumentChunk.chunking_version == chunking_version)

    total = base_query.count()
    embedded = base_query.filter(DocumentChunk.embedding.isnot(None)).count()
    unembedded = total - embedded
    return {
        "total_chunks": total,
        "embedded_chunks": embedded,
        "unembedded_chunks": unembedded,
    }


# ---------------------------------------------------------------------------
# Semantic Retrieval helpers
# ---------------------------------------------------------------------------

MAX_TOP_K = 100


def search_similar_chunks(
    session: Session,
    query_vector: Sequence[float],
    top_k: int = 5,
    embedding_model: Optional[str] = None,
    embedding_dim: Optional[int] = DEFAULT_EMBEDDING_DIM,
    document_id: Optional[uuid.UUID] = None,
) -> list[tuple[DocumentChunk, Document, float]]:
    """Search for most similar document chunks using pgvector cosine distance.

    Args:
        session: SQLAlchemy session.
        query_vector: Validated 768-dimensional float sequence.
        top_k: Number of nearest neighbors to retrieve (default: 5, max: 100).
        embedding_model: Optional model identifier filter (e.g. 'gemini-embedding-001').
        embedding_dim: Optional dimension filter (default: 768).
        document_id: Optional UUID filter for a specific document.

    Returns:
        List of tuples: (DocumentChunk, Document, cosine_distance: float)
        ordered by ascending cosine distance (most similar first).
        Ties are broken deterministically by (document_id, chunk_index).

    Raises:
        ValueError: If query_vector is invalid/wrong dimension, or top_k is out of range.
    """
    if not isinstance(top_k, int) or top_k < 1:
        raise ValueError(f"top_k must be a positive integer >= 1, got {top_k}")
    if top_k > MAX_TOP_K:
        raise ValueError(f"top_k cannot exceed {MAX_TOP_K}, got {top_k}")

    expected_dim = embedding_dim if embedding_dim is not None else DEFAULT_EMBEDDING_DIM
    clean_vec = validate_embedding(query_vector, expected_dim=expected_dim)

    dist_expr = DocumentChunk.embedding.cosine_distance(clean_vec).label("distance")

    query = (
        session.query(DocumentChunk, Document, dist_expr)
        .join(Document, DocumentChunk.document_id == Document.id)
        .filter(DocumentChunk.embedding.isnot(None))
    )

    if embedding_model is not None:
        query = query.filter(DocumentChunk.embedding_model == embedding_model)

    if embedding_dim is not None:
        query = query.filter(DocumentChunk.embedding_dim == embedding_dim)

    if document_id is not None:
        query = query.filter(DocumentChunk.document_id == document_id)

    results = (
        query.order_by(
            dist_expr.asc(),
            DocumentChunk.document_id.asc(),
            DocumentChunk.chunk_index.asc(),
        )
        .limit(top_k)
        .all()
    )

    return [(chunk, doc, float(dist)) for chunk, doc, dist in results]

