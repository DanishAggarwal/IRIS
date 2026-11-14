"""Tests for IRIS Milestone 7 Semantic Retrieval.

Covers:
- Query validation (empty, whitespace, non-string).
- Query embedding integration using mocked Gemini API client.
- Correct model ('gemini-embedding-001') and task type ('RETRIEVAL_QUERY').
- Vector dimension validation and non-finite rejection.
- Cosine distance ordering and deterministic tie-breaking.
- Top-K behavior (bounds, clipping, limits).
- Excluding NULL embeddings.
- Model and dimension filtering.
- Empty database / empty result behavior.
- Document and chunk metadata preservation (filename, page ranges, page_spans, has_table).
- Retrieval CLI execution and formatting.
- Evaluation metric calculations and hit detection.
"""

from io import StringIO
import json
from unittest.mock import MagicMock, patch
import uuid

import pytest

from database.connection import SessionLocal
from database.models import Document, DocumentChunk
from database.repository import (
    MAX_TOP_K,
    search_similar_chunks,
    store_chunk_embedding,
)
from google.genai import types
from retrieval.evaluate import check_hit
from retrieval.result import ChunkInfo, DocumentInfo, RetrievalResult
from retrieval.retriever import build_retrieval_result, retrieve_relevant_chunks
from retrieval.search import format_page_range, main as search_main


# ---------------------------------------------------------------------------
# Query & Parameter Validation Tests
# ---------------------------------------------------------------------------


def test_query_validation_rejects_empty_whitespace_and_invalid_types():
    """Verify that empty, whitespace, and non-string queries raise ValueError."""
    for invalid in ["", "   ", "\t\n", None, 123, [], {}]:
        with pytest.raises(ValueError, match="query"):
            retrieve_relevant_chunks(query=invalid)


def test_top_k_validation_bounds():
    """Verify top_k validates positive integer and maximum limit."""
    with pytest.raises(ValueError, match="top_k"):
        retrieve_relevant_chunks(query="test", top_k=0)

    with pytest.raises(ValueError, match="top_k"):
        retrieve_relevant_chunks(query="test", top_k=-5)

    with pytest.raises(ValueError, match="top_k"):
        retrieve_relevant_chunks(query="test", top_k=MAX_TOP_K + 1)

    with pytest.raises(ValueError, match="top_k"):
        retrieve_relevant_chunks(query="test", top_k="five")  # type: ignore


# ---------------------------------------------------------------------------
# Query Embedding & Task Type Tests (Mocked API)
# ---------------------------------------------------------------------------


def test_query_embedding_uses_retrieval_query_task_type():
    """Verify embed_query passes task_type='RETRIEVAL_QUERY' and 768 dimensions."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_embedding = MagicMock()
    mock_embedding.values = [0.01] * 768
    mock_response.embeddings = [mock_embedding]
    mock_client.models.embed_content.return_value = mock_response

    results = retrieve_relevant_chunks(
        query="What are the course objectives?",
        top_k=2,
        client=mock_client,
    )

    mock_client.models.embed_content.assert_called_once()
    call_kwargs = mock_client.models.embed_content.call_args.kwargs
    assert call_kwargs["model"] == "gemini-embedding-001"
    assert call_kwargs["contents"] == "What are the course objectives?"

    config = call_kwargs["config"]
    assert isinstance(config, types.EmbedContentConfig)
    assert config.task_type == "RETRIEVAL_QUERY"
    assert config.output_dimensionality == 768

    assert len(results) <= 2
    for r in results:
        assert isinstance(r, RetrievalResult)
        assert r.embedding_model == "gemini-embedding-001"
        assert r.embedding_dim == 768


# ---------------------------------------------------------------------------
# Vector Dimension & Rejection Tests
# ---------------------------------------------------------------------------


def test_search_similar_chunks_rejects_wrong_dimension():
    """search_similar_chunks must reject vectors whose length != expected_dim."""
    session = SessionLocal()
    try:
        with pytest.raises(ValueError, match="Embedding dimension mismatch"):
            search_similar_chunks(session=session, query_vector=[0.1] * 512, embedding_dim=768)

        with pytest.raises(ValueError, match="Embedding dimension mismatch"):
            search_similar_chunks(session=session, query_vector=[0.1] * 769, embedding_dim=768)
    finally:
        session.close()


def test_search_similar_chunks_rejects_nan_and_infinity():
    """search_similar_chunks must reject non-finite vector components."""
    session = SessionLocal()
    try:
        nan_vec = [0.1] * 768
        nan_vec[10] = float("nan")
        with pytest.raises(ValueError, match="non-finite"):
            search_similar_chunks(session=session, query_vector=nan_vec, embedding_dim=768)

        inf_vec = [0.1] * 768
        inf_vec[42] = float("inf")
        with pytest.raises(ValueError, match="non-finite"):
            search_similar_chunks(session=session, query_vector=inf_vec, embedding_dim=768)
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Nearest Neighbor, Ordering & Tie-Breaking Tests (Database Integration)
# ---------------------------------------------------------------------------


def test_cosine_distance_ordering_and_tie_breaking():
    """Verify chunks are returned strictly in ascending cosine distance order.

    When distances tie, ordering must be deterministically sorted by document_id and chunk_index.
    """
    session = SessionLocal()
    try:
        # Fetch an existing chunk embedding to use as a probe
        chunk = session.query(DocumentChunk).filter(DocumentChunk.embedding.isnot(None)).first()
        assert chunk is not None

        results = search_similar_chunks(
            session=session,
            query_vector=chunk.embedding,
            top_k=10,
        )

        assert len(results) > 0
        distances = [dist for _, _, dist in results]

        # Top result matching its own embedding must have cosine distance ~0.0
        assert pytest.approx(distances[0], abs=1e-5) == 0.0

        # Check ascending order
        for i in range(len(distances) - 1):
            assert distances[i] <= distances[i + 1], "Results must be sorted by ascending cosine distance"

        # Check tie breaking
        for i in range(len(results) - 1):
            c_curr, d_curr, dist_curr = results[i]
            c_next, d_next, dist_next = results[i + 1]
            if abs(dist_curr - dist_next) < 1e-9:
                key_curr = (c_curr.document_id, c_curr.chunk_index)
                key_next = (c_next.document_id, c_next.chunk_index)
                assert key_curr <= key_next, "Tied distances must break ties deterministically"
    finally:
        session.close()


def test_top_k_limits_result_count():
    """Verify top_k parameter strictly controls maximum returned rows."""
    session = SessionLocal()
    try:
        chunk = session.query(DocumentChunk).filter(DocumentChunk.embedding.isnot(None)).first()
        for k in [1, 3, 7]:
            res = search_similar_chunks(session=session, query_vector=chunk.embedding, top_k=k)
            assert len(res) == k
    finally:
        session.close()


def test_excluding_null_embeddings():
    """Verify search_similar_chunks excludes any chunk whose embedding is NULL."""
    session = SessionLocal()
    try:
        doc = session.query(Document).first()
        assert doc is not None

        # Insert a temporary un-embedded chunk
        unembedded = DocumentChunk(
            document_id=doc.id,
            chunk_index=99999,
            chunk_text="Temporary unembedded chunk for exclusion test",
            start_page=1,
            end_page=1,
            char_count=45,
            token_count=10,
            chunking_version="test-chunk-v1",
            embedding=None,
        )
        session.add(unembedded)
        session.flush()

        probe_chunk = session.query(DocumentChunk).filter(DocumentChunk.embedding.isnot(None)).first()
        res = search_similar_chunks(session=session, query_vector=probe_chunk.embedding, top_k=50)

        retrieved_ids = [c.id for c, _, _ in res]
        assert unembedded.id not in retrieved_ids, "Unembedded chunk with NULL embedding must never be retrieved"
    finally:
        session.rollback()
        session.close()


def test_filtering_by_model_and_dimension():
    """Verify searching filters by embedding_model and embedding_dim."""
    session = SessionLocal()
    try:
        chunk = session.query(DocumentChunk).filter(DocumentChunk.embedding.isnot(None)).first()

        # Non-matching model filter should return 0 results
        res_wrong_model = search_similar_chunks(
            session=session,
            query_vector=chunk.embedding,
            embedding_model="non-existent-model",
            top_k=5,
        )
        assert len(res_wrong_model) == 0

        # Matching model filter should return results
        res_matching = search_similar_chunks(
            session=session,
            query_vector=chunk.embedding,
            embedding_model="gemini-embedding-001",
            top_k=5,
        )
        assert len(res_matching) > 0
    finally:
        session.close()


def test_empty_database_behavior():
    """Verify querying an empty document scope returns empty list without error."""
    session = SessionLocal()
    try:
        fake_id = uuid.uuid4()
        chunk = session.query(DocumentChunk).filter(DocumentChunk.embedding.isnot(None)).first()
        res = search_similar_chunks(
            session=session,
            query_vector=chunk.embedding,
            document_id=fake_id,
            top_k=5,
        )
        assert res == []
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Metadata & Provenance Preservation Tests
# ---------------------------------------------------------------------------


def test_retrieval_result_provenance_preservation():
    """Verify RetrievalResult correctly reflects Document and Chunk metadata."""
    session = SessionLocal()
    try:
        chunk = session.query(DocumentChunk).filter(DocumentChunk.embedding.isnot(None)).first()
        doc = session.get(Document, chunk.document_id)

        res = build_retrieval_result(
            rank=1,
            chunk=chunk,
            document=doc,
            distance=0.15,
            model="gemini-embedding-001",
            dimension=768,
        )

        assert res.rank == 1
        assert res.cosine_distance == 0.15
        assert pytest.approx(res.similarity_score, abs=1e-5) == 0.85
        assert res.document.filename == doc.filename
        assert res.document.id == doc.id
        assert res.chunk.id == chunk.id
        assert res.chunk.chunk_index == chunk.chunk_index
        assert res.chunk.chunk_text == chunk.chunk_text
        assert res.chunk.start_page == chunk.start_page
        assert res.chunk.end_page == chunk.end_page
        assert res.chunk.token_count == chunk.token_count

        # Check page_spans and table metadata
        meta = chunk.metadata_ or {}
        assert res.chunk.page_spans == meta.get("page_spans", [])
        assert res.chunk.has_table == bool(meta.get("has_table", False))

        # Check serialization
        d = res.to_dict()
        assert d["rank"] == 1
        assert d["document"]["filename"] == doc.filename
        assert d["chunk"]["id"] == str(chunk.id)
    finally:
        session.close()


# ---------------------------------------------------------------------------
# CLI & Terminal Formatter Tests
# ---------------------------------------------------------------------------


def test_format_page_range_helper():
    """Verify page range formatting matches 1-based human convention."""
    assert format_page_range(3, 3) == "Page 3"
    assert format_page_range(11, 14) == "Pages 11–14"


def test_retrieval_cli_output(capsys):
    """Verify search CLI outputs formatted rankings and source locations."""
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_emb = MagicMock()
    mock_emb.values = [0.05] * 768
    mock_resp.embeddings = [mock_emb]
    mock_client.models.embed_content.return_value = mock_resp

    with patch("ingestion.embedding_provider._get_client", return_value=mock_client):
        ret = search_main(["What are course objectives?", "--top-k", "2"])
        assert ret == 0

        captured = capsys.readouterr()
        assert "IRIS SEMANTIC RETRIEVAL" in captured.out
        assert "[Rank 1 / 2]" in captured.out
        assert "Cosine Distance:" in captured.out
        assert "Source  :" in captured.out
        assert "Location:" in captured.out


def test_retrieval_cli_json_flag(capsys):
    """Verify search CLI --json flag produces valid parseable JSON."""
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_emb = MagicMock()
    mock_emb.values = [0.05] * 768
    mock_resp.embeddings = [mock_emb]
    mock_client.models.embed_content.return_value = mock_resp

    with patch("ingestion.embedding_provider._get_client", return_value=mock_client):
        ret = search_main(["Course objectives", "--top-k", "1", "--json"])
        assert ret == 0

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["query"] == "Course objectives"
        assert data["top_k"] == 1
        assert len(data["results"]) == 1
        assert "document" in data["results"][0]
        assert "chunk" in data["results"][0]


# ---------------------------------------------------------------------------
# Evaluation Metric Helper Tests
# ---------------------------------------------------------------------------


def test_check_hit_interval_overlap():
    """Verify check_hit identifies overlapping intervals and rejects non-overlapping."""
    doc_info = DocumentInfo(id=uuid.uuid4(), filename="test_doc.pdf")
    chunk_info = ChunkInfo(
        id=uuid.uuid4(),
        chunk_index=0,
        chunk_text="text",
        section_title=None,
        start_page=10,
        end_page=12,
        page_spans=[],
        has_table=False,
        chunking_version="v1",
        char_count=4,
        token_count=1,
    )
    res = RetrievalResult(
        rank=1,
        cosine_distance=0.1,
        similarity_score=0.9,
        embedding_model="test",
        embedding_dim=768,
        document=doc_info,
        chunk=chunk_info,
    )

    # Matching doc and overlapping pages
    assert check_hit(res, expected_doc="test_doc.pdf", exp_pages=[11, 11]) is True
    assert check_hit(res, expected_doc="test_doc.pdf", exp_pages=[12, 15]) is True
    assert check_hit(res, expected_doc="test_doc.pdf", exp_pages=[8, 10]) is True

    # Disjoint pages
    assert check_hit(res, expected_doc="test_doc.pdf", exp_pages=[1, 9]) is False
    assert check_hit(res, expected_doc="test_doc.pdf", exp_pages=[13, 20]) is False

    # Wrong doc
    assert check_hit(res, expected_doc="other_doc.pdf", exp_pages=[10, 12]) is False

    # Acceptable sources fallback
    assert check_hit(
        res,
        expected_doc="other_doc.pdf",
        exp_pages=[1, 2],
        acceptable_sources=[{"document": "test_doc.pdf", "pages": [10, 15]}],
    ) is True
