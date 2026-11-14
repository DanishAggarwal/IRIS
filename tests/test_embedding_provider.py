"""Unit tests for Milestone 6: Gemini Embedding Provider and Pipeline.

All tests in this module use mocked Gemini API client responses so they can run
deterministically offline without consuming quota or requiring active network access.
"""

import math
import uuid
from unittest.mock import MagicMock, patch

import pytest
from google.genai import errors

from database.connection import SessionLocal
from database.models import Document, DocumentChunk
from database.repository import (
    get_chunk_by_id,
    replace_document_chunks,
    upsert_document,
)
from ingestion.embed_chunks import run_embedding_pipeline
from ingestion.embedding_provider import (
    DEFAULT_MODEL,
    embed_documents,
    embed_query,
    get_embedding_config,
)


class MockEmbeddingItem:
    def __init__(self, values):
        self.values = values


class MockEmbedResponse:
    def __init__(self, embeddings):
        self.embeddings = embeddings
        self.usage_metadata = None


@pytest.fixture
def mock_genai_client():
    """Create a mock genai.Client with embed_content configured."""
    client = MagicMock()
    # Default behavior: returns valid 768-dim float vector for each content item
    def side_effect(model, contents, config):
        items = contents if isinstance(contents, list) else [contents]
        embeddings = [MockEmbeddingItem([0.01 * (i % 10) for i in range(config.output_dimensionality)]) for _ in items]
        return MockEmbedResponse(embeddings)

    client.models.embed_content.side_effect = side_effect
    return client


# ---------------------------------------------------------------------------
# Unit tests: Provider configuration & task types
# ---------------------------------------------------------------------------


def test_missing_api_key_raises_environment_error(monkeypatch):
    """Missing GEMINI_API_KEY must raise a clear EnvironmentError."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(EnvironmentError, match="GEMINI_API_KEY is not set"):
        embed_documents(["Test text"], client=None)

    with pytest.raises(EnvironmentError, match="GEMINI_API_KEY is not set"):
        embed_query("Test query", client=None)


def test_embed_documents_correct_task_type_and_model(mock_genai_client):
    """embed_documents must call API with RETRIEVAL_DOCUMENT, 768 dims, and correct model."""
    texts = ["Document chunk one text", "Document chunk two text"]
    results = embed_documents(texts, batch_size=2, client=mock_genai_client)

    assert len(results) == 2
    assert len(results[0]) == 768
    assert len(results[1]) == 768

    mock_genai_client.models.embed_content.assert_called_once()
    _, kwargs = mock_genai_client.models.embed_content.call_args
    assert kwargs["model"] == DEFAULT_MODEL
    assert kwargs["contents"] == texts
    assert kwargs["config"].task_type == "RETRIEVAL_DOCUMENT"
    assert kwargs["config"].output_dimensionality == 768


def test_embed_query_correct_task_type_and_model(mock_genai_client):
    """embed_query must call API with RETRIEVAL_QUERY, 768 dims, and correct model."""
    query = "What are the course objectives?"
    result = embed_query(query, client=mock_genai_client)

    assert len(result) == 768
    assert isinstance(result, list)

    mock_genai_client.models.embed_content.assert_called_once()
    _, kwargs = mock_genai_client.models.embed_content.call_args
    assert kwargs["model"] == DEFAULT_MODEL
    assert kwargs["contents"] == query
    assert kwargs["config"].task_type == "RETRIEVAL_QUERY"
    assert kwargs["config"].output_dimensionality == 768


def test_reject_empty_and_whitespace_inputs(mock_genai_client):
    """Empty or blank inputs must be rejected with ValueError before API calls."""
    with pytest.raises(ValueError, match="empty or non-string"):
        embed_query("", client=mock_genai_client)

    with pytest.raises(ValueError, match="empty or non-string"):
        embed_query("   ", client=mock_genai_client)

    with pytest.raises(ValueError, match="empty or non-string"):
        embed_documents(["Valid text", ""], client=mock_genai_client)

    assert mock_genai_client.models.embed_content.call_count == 0


def test_768_dimensional_output_validation():
    """Provider must reject API responses with dimensions != 768."""
    bad_client = MagicMock()
    bad_client.models.embed_content.return_value = MockEmbedResponse(
        [MockEmbeddingItem([0.1] * 512)]  # 512 instead of 768
    )

    with pytest.raises(ValueError, match="dimension mismatch: expected 768, got 512"):
        embed_documents(["Valid text"], client=bad_client)


def test_reject_nan_and_infinity_in_response():
    """Provider must reject non-finite vectors returned by the API."""
    nan_vec = [0.1] * 768
    nan_vec[15] = float("nan")

    bad_client = MagicMock()
    bad_client.models.embed_content.return_value = MockEmbedResponse(
        [MockEmbeddingItem(nan_vec)]
    )

    with pytest.raises(ValueError, match="non-finite value"):
        embed_documents(["Valid text"], client=bad_client)


def test_retry_on_transient_error(mock_genai_client):
    """Transient server errors (5xx) must retry with exponential backoff and succeed."""
    call_count = 0

    def flaky_embed(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            # First 2 calls fail with ServerError
            raise errors.ServerError(500, {"message": "Transient internal error"})
        return MockEmbedResponse([MockEmbeddingItem([0.05] * 768)])

    mock_genai_client.models.embed_content.side_effect = flaky_embed

    with patch("time.sleep") as mock_sleep:
        results = embed_documents(["Some text"], client=mock_genai_client)

    assert len(results) == 1
    assert call_count == 3
    assert mock_sleep.call_count == 2


def test_permanent_error_no_indefinite_retry(mock_genai_client):
    """Permanent client errors (e.g. 400 Bad Request) must fail immediately without retry."""
    call_count = 0

    def permanent_fail(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        raise errors.ClientError(400, {"message": "Invalid argument"})

    mock_genai_client.models.embed_content.side_effect = permanent_fail

    with patch("time.sleep") as mock_sleep:
        with pytest.raises(errors.ClientError):
            embed_documents(["Some text"], client=mock_genai_client)

    assert call_count == 1
    assert mock_sleep.call_count == 0


# ---------------------------------------------------------------------------
# Integration tests: Incremental Pipeline Logic (Mocked API)
# ---------------------------------------------------------------------------


def test_incremental_pipeline_skips_already_embedded(monkeypatch):
    """Pipeline skips chunks that already have valid embeddings."""
    mock_vec = [0.02] * 768
    monkeypatch.setattr(
        "ingestion.embed_chunks.embed_documents",
        lambda texts, batch_size: [mock_vec for _ in texts],
    )

    with SessionLocal() as session:
        sha = f"test_pipe_sha_{uuid.uuid4().hex[:12]}"
        doc = upsert_document(session, filename="test_pipeline.pdf", sha256=sha)
        session.commit()

        chunks_data = [
            {"chunk_index": i, "chunk_text": f"Pipeline chunk {i}", "start_page": 1, "end_page": 1, "char_count": 20, "token_count": 5}
            for i in range(2)
        ]
        chunks = replace_document_chunks(session, doc.id, "chunk-v1", chunks_data)
        # Pre-embed chunk 0
        chunks[0].embedding = mock_vec
        chunks[0].embedding_model = "test-model"
        chunks[0].embedding_dim = 768
        session.commit()

        try:
            summary = run_embedding_pipeline(document_id=doc.id, batch_size=5)
            assert summary["embedded"] == 1
            assert summary["skipped"] == 1
            assert summary["failed"] == 0

            # Second run: now both are embedded, so both are skipped
            summary_2 = run_embedding_pipeline(document_id=doc.id, batch_size=5)
            assert summary_2["embedded"] == 0
            assert summary_2["skipped"] == 2
        finally:
            session.delete(doc)
            session.commit()


def test_pipeline_failure_isolation(monkeypatch):
    """If a batch fails, previously committed batches remain intact and safe."""
    batch_call_count = 0

    def mock_embed(texts, batch_size):
        nonlocal batch_call_count
        batch_call_count += 1
        if batch_call_count == 2:
            raise RuntimeError("API failure on second batch")
        return [[0.01] * 768 for _ in texts]

    monkeypatch.setattr("ingestion.embed_chunks.embed_documents", mock_embed)

    with SessionLocal() as session:
        sha = f"test_iso_sha_{uuid.uuid4().hex[:12]}"
        doc = upsert_document(session, filename="test_isolation.pdf", sha256=sha)
        session.commit()

        chunks_data = [
            {"chunk_index": i, "chunk_text": f"Iso chunk {i}", "start_page": 1, "end_page": 1, "char_count": 15, "token_count": 4}
            for i in range(4)
        ]
        chunks = replace_document_chunks(session, doc.id, "chunk-v1", chunks_data)
        session.commit()
        chunk_ids = [c.id for c in chunks]

        try:
            # Run with batch_size=2: first batch (chunks 0, 1) succeeds and commits; second batch (chunks 2, 3) fails
            summary = run_embedding_pipeline(document_id=doc.id, batch_size=2)
            assert summary["embedded"] == 2
            assert summary["failed"] == 2

            session.expire_all()
            c0 = get_chunk_by_id(session, chunk_ids[0])
            c1 = get_chunk_by_id(session, chunk_ids[1])
            c2 = get_chunk_by_id(session, chunk_ids[2])
            c3 = get_chunk_by_id(session, chunk_ids[3])

            # Chunks 0 and 1 are persisted and valid
            assert c0.embedding is not None and len(c0.embedding) == 768
            assert c1.embedding is not None and len(c1.embedding) == 768
            # Chunks 2 and 3 remain unembedded (None)
            assert c2.embedding is None
            assert c3.embedding is None

        finally:
            session.delete(doc)
            session.commit()
