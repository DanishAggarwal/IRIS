"""Unit and integration tests for Milestone 5: Embedding Database Foundation.

Tests cover:
- Persisting a valid 768-dimensional embedding.
- Reading it back correctly.
- Identifying pending/unembedded chunks and embedding status counts.
- Rejecting wrong dimensions.
- Rejecting NaN, infinity, and malformed vector values.
- Preserving existing chunk text, page provenance, and metadata.
- Transaction rollback on failure.
- Updating an existing embedding safely.
- Batch embedding persistence atomicity.
"""

import math
import uuid
import pytest
from database.connection import SessionLocal
from database.models import Document, DocumentChunk
from database.repository import (
    upsert_document,
    replace_document_chunks,
    store_chunk_embedding,
    store_chunk_embeddings_batch,
    get_unembedded_chunks,
    get_chunk_embedding_status,
    get_chunk_by_id,
    validate_embedding,
    DEFAULT_EMBEDDING_DIM,
)


@pytest.fixture
def db_session():
    """Provide a transactional database session for tests and clean up created test documents."""
    session = SessionLocal()
    created_docs = []

    def register_doc(doc):
        created_docs.append(doc.id)
        return doc

    session.register_doc = register_doc
    yield session

    try:
        if created_docs:
            for doc_id in created_docs:
                doc = session.get(Document, doc_id)
                if doc:
                    session.delete(doc)
            session.commit()
    finally:
        session.close()


@pytest.fixture
def sample_test_chunk(db_session):
    """Create an isolated test document and chunk for testing."""
    sha = f"test_emb_sha_{uuid.uuid4().hex[:12]}"
    doc = upsert_document(db_session, filename="test_embedding_doc.pdf", sha256=sha)
    db_session.commit()
    db_session.register_doc(doc)

    chunk_data = [
        {
            "chunk_index": 0,
            "chunk_text": "Sample text for embedding repository tests with institutional context.",
            "start_page": 2,
            "end_page": 3,
            "char_count": 70,
            "token_count": 18,
            "section_title": "Course Structure",
            "metadata": {
                "has_table": True,
                "page_spans": [
                    {"page": 2, "char_start": 0, "char_end": 35},
                    {"page": 3, "char_start": 37, "char_end": 70},
                ],
            },
        }
    ]
    chunks = replace_document_chunks(
        session=db_session,
        document_id=doc.id,
        chunking_version="chunk-v1",
        chunks_data=chunk_data,
    )
    db_session.commit()
    return doc, chunks[0]


# ---------------------------------------------------------------------------
# Unit tests: vector validation
# ---------------------------------------------------------------------------


def test_validate_embedding_valid():
    """A valid 768-dimensional float list passes validation."""
    vec = [float(i) * 0.001 for i in range(768)]
    clean = validate_embedding(vec, expected_dim=768)
    assert len(clean) == 768
    assert isinstance(clean, list)
    assert clean[0] == 0.0
    assert pytest.approx(clean[1], abs=1e-6) == 0.001


def test_validate_embedding_rejects_wrong_dimension():
    """Vectors with dimensions != 768 must be rejected."""
    short_vec = [0.1] * 512
    with pytest.raises(ValueError, match="Embedding dimension mismatch: expected 768, got 512"):
        validate_embedding(short_vec, expected_dim=768)

    long_vec = [0.1] * 769
    with pytest.raises(ValueError, match="Embedding dimension mismatch: expected 768, got 769"):
        validate_embedding(long_vec, expected_dim=768)


def test_validate_embedding_rejects_nan_and_inf():
    """Vectors containing NaN or +/-Infinity must be rejected."""
    vec_nan = [0.1] * 768
    vec_nan[42] = float("nan")
    with pytest.raises(ValueError, match="non-finite value.*at index 42"):
        validate_embedding(vec_nan, expected_dim=768)

    vec_inf = [0.1] * 768
    vec_inf[100] = float("inf")
    with pytest.raises(ValueError, match="non-finite value.*at index 100"):
        validate_embedding(vec_inf, expected_dim=768)

    vec_neg_inf = [0.1] * 768
    vec_neg_inf[200] = float("-inf")
    with pytest.raises(ValueError, match="non-finite value.*at index 200"):
        validate_embedding(vec_neg_inf, expected_dim=768)


def test_validate_embedding_rejects_malformed_types():
    """Non-sequences and non-numeric types must be rejected."""
    with pytest.raises(ValueError, match="Embedding vector cannot be None"):
        validate_embedding(None)

    with pytest.raises(ValueError, match="sequence of numeric floats"):
        validate_embedding("invalid_string_instead_of_vector")

    with pytest.raises(ValueError, match="non-numeric"):
        validate_embedding(["not_a_number"] * 768)


# ---------------------------------------------------------------------------
# Integration tests: persistence, retrieval, provenance, status
# ---------------------------------------------------------------------------


def test_persist_and_read_768_dim_embedding(db_session, sample_test_chunk):
    """Store a 768-dim embedding and read it back accurately from the database."""
    doc, chunk = sample_test_chunk
    test_vec = [math.sin(i) * 0.1 for i in range(768)]
    model_name = "test-embedding-004"

    updated = store_chunk_embedding(
        session=db_session,
        chunk_id=chunk.id,
        embedding=test_vec,
        embedding_model=model_name,
        embedding_dim=768,
    )
    db_session.commit()

    assert updated.embedding is not None
    assert len(updated.embedding) == 768
    assert updated.embedding_model == model_name
    assert updated.embedding_dim == 768

    # Query afresh in a separate lookup
    fetched = get_chunk_by_id(db_session, chunk.id)
    assert fetched is not None
    assert fetched.embedding is not None
    assert len(fetched.embedding) == 768
    assert fetched.embedding_model == model_name
    assert fetched.embedding_dim == 768
    # Validate vector numerical fidelity
    for actual, expected in zip(fetched.embedding, test_vec):
        assert pytest.approx(actual, abs=1e-5) == expected


def test_preserve_chunk_text_provenance_and_metadata(db_session, sample_test_chunk):
    """Storing an embedding must not alter chunk_text, page numbers, page_spans, or metadata."""
    doc, chunk = sample_test_chunk
    original_text = chunk.chunk_text
    original_start = chunk.start_page
    original_end = chunk.end_page
    original_section = chunk.section_title
    original_meta = dict(chunk.metadata_)
    original_version = chunk.chunking_version
    original_id = chunk.id

    test_vec = [0.05] * 768
    store_chunk_embedding(
        session=db_session,
        chunk_id=chunk.id,
        embedding=test_vec,
        embedding_model="test-embedding-model",
    )
    db_session.commit()

    reloaded = get_chunk_by_id(db_session, original_id)
    assert reloaded.id == original_id
    assert reloaded.chunk_text == original_text
    assert reloaded.start_page == original_start
    assert reloaded.end_page == original_end
    assert reloaded.section_title == original_section
    assert reloaded.metadata_ == original_meta
    assert reloaded.chunking_version == original_version


def test_identifying_pending_unembedded_chunks(db_session):
    """get_unembedded_chunks and get_chunk_embedding_status must accurately identify pending chunks."""
    sha = f"test_unemb_sha_{uuid.uuid4().hex[:12]}"
    doc = upsert_document(db_session, filename="test_unembedded.pdf", sha256=sha)
    db_session.commit()
    db_session.register_doc(doc)

    # Create 3 chunks, initially with embedding=None
    chunks_data = [
        {
            "chunk_index": i,
            "chunk_text": f"Chunk text index {i}",
            "start_page": 1,
            "end_page": 1,
            "char_count": 20,
            "token_count": 5,
        }
        for i in range(3)
    ]
    chunks = replace_document_chunks(db_session, doc.id, "chunk-v1", chunks_data)
    db_session.commit()

    # Check initially all 3 are unembedded
    unembedded = get_unembedded_chunks(db_session, document_id=doc.id)
    assert len(unembedded) == 3
    assert [c.chunk_index for c in unembedded] == [0, 1, 2]

    status = get_chunk_embedding_status(db_session, document_id=doc.id)
    assert status == {"total_chunks": 3, "embedded_chunks": 0, "unembedded_chunks": 3}

    # Embed chunk 0 and chunk 2
    dummy_vec = [0.02] * 768
    store_chunk_embedding(db_session, chunks[0].id, dummy_vec, "test-model")
    store_chunk_embedding(db_session, chunks[2].id, dummy_vec, "test-model")
    db_session.commit()

    # Now only chunk 1 is unembedded
    unembedded_after = get_unembedded_chunks(db_session, document_id=doc.id)
    assert len(unembedded_after) == 1
    assert unembedded_after[0].chunk_index == 1

    status_after = get_chunk_embedding_status(db_session, document_id=doc.id)
    assert status_after == {"total_chunks": 3, "embedded_chunks": 2, "unembedded_chunks": 1}


def test_reject_wrong_dimension_in_store(db_session, sample_test_chunk):
    """store_chunk_embedding must reject invalid dimensions without modifying the chunk."""
    doc, chunk = sample_test_chunk
    with pytest.raises(ValueError, match="dimension mismatch"):
        store_chunk_embedding(
            session=db_session,
            chunk_id=chunk.id,
            embedding=[0.1] * 128,  # Wrong dimension (128 instead of 768)
            embedding_model="test-model",
            embedding_dim=768,
        )

    # Verify chunk remained unmodified
    reloaded = get_chunk_by_id(db_session, chunk.id)
    assert reloaded.embedding is None


def test_reject_nan_infinity_in_store(db_session, sample_test_chunk):
    """store_chunk_embedding must reject vectors containing NaN or Inf without saving."""
    doc, chunk = sample_test_chunk
    bad_vec = [0.1] * 768
    bad_vec[50] = float("nan")

    with pytest.raises(ValueError, match="non-finite value"):
        store_chunk_embedding(
            session=db_session,
            chunk_id=chunk.id,
            embedding=bad_vec,
            embedding_model="test-model",
        )

    reloaded = get_chunk_by_id(db_session, chunk.id)
    assert reloaded.embedding is None


def test_update_existing_embedding_safely(db_session, sample_test_chunk):
    """Updating an existing embedding overwrites vector and model while preserving chunk data."""
    doc, chunk = sample_test_chunk
    vec_v1 = [0.1] * 768
    store_chunk_embedding(db_session, chunk.id, vec_v1, "model-v1", 768)
    db_session.commit()

    # Update with v2
    vec_v2 = [0.2] * 768
    store_chunk_embedding(db_session, chunk.id, vec_v2, "model-v2", 768)
    db_session.commit()

    reloaded = get_chunk_by_id(db_session, chunk.id)
    assert reloaded.embedding_model == "model-v2"
    assert pytest.approx(reloaded.embedding[0], abs=1e-5) == 0.2


def test_transaction_rollback_on_failure(db_session, sample_test_chunk):
    """A failed operation rolled back by the session leaves no partial updates."""
    doc, chunk = sample_test_chunk
    original_meta = dict(chunk.metadata_)

    try:
        # Perform valid change in session
        chunk.embedding_model = "temporary_uncommitted_model"
        # Then trigger an error
        raise RuntimeError("Simulated failure during pipeline")
    except RuntimeError:
        db_session.rollback()

    reloaded = get_chunk_by_id(db_session, chunk.id)
    assert reloaded.embedding_model is None
    assert reloaded.embedding is None
    assert reloaded.metadata_ == original_meta


def test_store_chunk_embeddings_batch(db_session):
    """Batch storing embeddings commits all valid items and rejects atomically on error."""
    sha = f"test_batch_sha_{uuid.uuid4().hex[:12]}"
    doc = upsert_document(db_session, filename="test_batch.pdf", sha256=sha)
    db_session.commit()
    db_session.register_doc(doc)

    chunks_data = [
        {"chunk_index": i, "chunk_text": f"Batch chunk {i}", "start_page": 1, "end_page": 1, "char_count": 15, "token_count": 4}
        for i in range(2)
    ]
    chunks = replace_document_chunks(db_session, doc.id, "chunk-v1", chunks_data)
    db_session.commit()

    vec_valid = [0.03] * 768
    updates = [
        {"chunk_id": chunks[0].id, "embedding": vec_valid, "embedding_model": "batch-model"},
        {"chunk_id": chunks[1].id, "embedding": vec_valid, "embedding_model": "batch-model"},
    ]
    count = store_chunk_embeddings_batch(db_session, updates)
    db_session.commit()

    assert count == 2
    c0 = get_chunk_by_id(db_session, chunks[0].id)
    c1 = get_chunk_by_id(db_session, chunks[1].id)
    assert c0.embedding is not None and len(c0.embedding) == 768
    assert c1.embedding is not None and len(c1.embedding) == 768

    # Test atomicity: batch containing one invalid item must fail completely
    bad_updates = [
        {"chunk_id": chunks[0].id, "embedding": [0.05] * 768, "embedding_model": "batch-model-2"},
        {"chunk_id": chunks[1].id, "embedding": [0.05] * 10, "embedding_model": "batch-model-2"},  # Bad dim
    ]
    with pytest.raises(ValueError, match="dimension mismatch"):
        store_chunk_embeddings_batch(db_session, bad_updates)

    db_session.rollback()

    # Verify chunk 0 was not partially updated to batch-model-2
    c0_after = get_chunk_by_id(db_session, chunks[0].id)
    assert c0_after.embedding_model == "batch-model"
