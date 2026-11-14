"""Tests for IRIS Milestone 9 FastAPI backend."""

from unittest.mock import MagicMock, patch
import uuid
import pytest
from fastapi.testclient import TestClient

from api.config import APISettings, get_api_settings
from api.dependencies import get_database_session
from api.main import create_application
from rag.models import AnswerStatus, Citation, RAGResponse


@pytest.fixture
def mock_db_session():
    """Fixture providing a mocked SQLAlchemy Session."""
    session = MagicMock()
    return session


@pytest.fixture
def client(mock_db_session):
    """Fixture providing a FastAPI TestClient with mocked database session dependency."""
    app = create_application()
    app.dependency_overrides[get_database_session] = lambda: mock_db_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Application & Documentation Tests
# ---------------------------------------------------------------------------


def test_application_startup_and_routes(client):
    """Verify application registers routes and OpenAPI docs properly."""
    resp_openapi = client.get("/openapi.json")
    assert resp_openapi.status_code == 200
    schema = resp_openapi.json()
    assert schema["info"]["title"] == "IRIS Institutional Document RAG API"
    assert "/health" in schema["paths"]
    assert "/health/ready" in schema["paths"]
    assert "/chat" in schema["paths"]

    resp_docs = client.get("/docs")
    assert resp_docs.status_code == 200

    resp_redoc = client.get("/redoc")
    assert resp_redoc.status_code == 200


# ---------------------------------------------------------------------------
# Health & Readiness Endpoints
# ---------------------------------------------------------------------------


def test_health_liveness_endpoint(client):
    """Verify /health returns 200 ok."""
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["service"] == "IRIS API"


def test_readiness_endpoint_healthy(client, mock_db_session):
    """Verify /health/ready returns 200 when database and configuration are available."""
    mock_db_session.execute.return_value = True

    with patch.dict("os.environ", {"GEMINI_API_KEY": "dummy_test_key"}):
        resp = client.get("/health/ready")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ready"
        assert data["database"] == "connected"
        assert data["configuration"] == "ready"
        assert data["detail"] is None


def test_readiness_endpoint_db_failure(client, mock_db_session):
    """Verify /health/ready returns 503 when database is unreachable."""
    mock_db_session.execute.side_effect = Exception("Database connection refused")

    with patch.dict("os.environ", {"GEMINI_API_KEY": "dummy_test_key"}):
        resp = client.get("/health/ready")
        assert resp.status_code == 503
        data = resp.json()
        assert data["status"] == "unavailable"
        assert data["database"] == "unavailable"
        assert "Database is unreachable" in data["detail"]


def test_readiness_endpoint_missing_api_key(client, mock_db_session):
    """Verify /health/ready returns 503 when GEMINI_API_KEY is missing."""
    mock_db_session.execute.return_value = True

    with patch.dict("os.environ", {"GEMINI_API_KEY": ""}):
        resp = client.get("/health/ready")
        assert resp.status_code == 503
        data = resp.json()
        assert data["status"] == "unavailable"
        assert data["configuration"] == "missing_api_key"
        assert "GEMINI_API_KEY is not configured" in data["detail"]


# ---------------------------------------------------------------------------
# Chat Request Validation Tests
# ---------------------------------------------------------------------------


def test_chat_rejects_empty_query(client):
    """Verify /chat rejects empty string queries with 422."""
    resp = client.post("/chat", json={"query": ""})
    assert resp.status_code == 422
    assert "detail" in resp.json()


def test_chat_rejects_whitespace_query(client):
    """Verify /chat rejects queries with only spaces with 422."""
    resp = client.post("/chat", json={"query": "    \t  \n "})
    assert resp.status_code == 422
    assert "Query cannot be empty or contain only whitespace" in resp.json()["detail"]


def test_chat_rejects_missing_query(client):
    """Verify /chat rejects requests missing the query field with 422."""
    resp = client.post("/chat", json={"top_k": 5})
    assert resp.status_code == 422


def test_chat_rejects_query_exceeding_max_length(client):
    """Verify /chat rejects queries exceeding max length with 422."""
    long_query = "word " * 250  # ~1250 characters
    resp = client.post("/chat", json={"query": long_query})
    assert resp.status_code == 422


def test_chat_rejects_invalid_top_k_bounds(client):
    """Verify /chat enforces top_k bounds (1 <= top_k <= 20)."""
    # top_k < 1
    resp_low = client.post("/chat", json={"query": "Valid query", "top_k": 0})
    assert resp_low.status_code == 422

    # top_k > 20
    resp_high = client.post("/chat", json={"query": "Valid query", "top_k": 25})
    assert resp_high.status_code == 422


# ---------------------------------------------------------------------------
# Chat RAG Pipeline Invocation & Response Handling Tests
# ---------------------------------------------------------------------------


def test_chat_answered_response(client):
    """Verify /chat returns structured answered response with verified citations."""
    mock_citation = Citation(
        document="CSE_syllabus_24.pdf",
        pages=[117],
        chunk_id=uuid.uuid4(),
        section_title="Unit 7",
        claim="Cloud Computing Objectives",
        is_valid=True,
        claim_supported=True,
    )
    mock_rag_response = RAGResponse(
        query="What are the course objectives of Cloud Computing?",
        status=AnswerStatus.ANSWERED.value,
        answer="Cloud Computing objectives include infrastructure security.",
        citations=[mock_citation],
        clarification_question=None,
        limitations=None,
        handoff_recommendation=None,
        retrieved_results=[MagicMock()],
    )

    with patch("api.routes.chat.answer_question", return_value=mock_rag_response) as mock_pipeline:
        resp = client.post(
            "/chat",
            json={"query": "What are the course objectives of Cloud Computing?", "top_k": 5},
        )
        assert resp.status_code == 200
        data = resp.json()

        assert data["query"] == "What are the course objectives of Cloud Computing?"
        assert data["status"] == "answered"
        assert "infrastructure security" in data["answer"]
        assert len(data["citations"]) == 1
        assert data["citations"][0]["document"] == "CSE_syllabus_24.pdf"
        assert data["citations"][0]["pages"] == [117]
        assert data["citations"][0]["section_title"] == "Unit 7"
        assert data["citations"][0]["is_valid"] is True
        assert data["citations"][0]["claim_supported"] is True
        assert data["retrieved_count"] == 1

        mock_pipeline.assert_called_once()


def test_chat_clarification_response(client):
    """Verify /chat returns clarification_needed with clarification question."""
    mock_rag_response = RAGResponse(
        query="What are the course objectives?",
        status=AnswerStatus.CLARIFICATION_NEEDED.value,
        answer="Multiple courses exist in the syllabus.",
        citations=[],
        clarification_question="Which specific course are you inquiring about?",
        limitations=None,
        handoff_recommendation=None,
        retrieved_results=[],
    )

    with patch("api.routes.chat.answer_question", return_value=mock_rag_response):
        resp = client.post("/chat", json={"query": "What are the course objectives?"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "clarification_needed"
        assert data["clarification_question"] == "Which specific course are you inquiring about?"
        assert data["citations"] == []


def test_chat_safe_handoff_response(client):
    """Verify /chat returns handoff_recommended with safe institutional office."""
    mock_rag_response = RAGResponse(
        query="What are the mess charges?",
        status=AnswerStatus.HANDOFF_RECOMMENDED.value,
        answer="Mess charges are not documented in the curriculum corpus.",
        citations=[],
        clarification_question=None,
        limitations="Corpus lacks hostel fees.",
        handoff_recommendation="Please verify with the hostel administration office.",
        retrieved_results=[],
    )

    with patch("api.routes.chat.answer_question", return_value=mock_rag_response):
        resp = client.post("/chat", json={"query": "What are the mess charges?"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "handoff_recommended"
        assert "hostel administration" in data["handoff_recommendation"]


def test_chat_ensures_no_insufficient_evidence_status_escapes(client):
    """Verify that if pipeline returns internal insufficient_evidence, API maps to handoff_recommended."""
    mock_rag_response = RAGResponse(
        query="What is the GPU driver version?",
        status="insufficient_evidence",
        answer="Hardware drivers are absent from course packs.",
        citations=[],
        clarification_question=None,
        limitations=None,
        handoff_recommendation="Please verify with the IT services department.",
        retrieved_results=[],
    )

    with patch("api.routes.chat.answer_question", return_value=mock_rag_response):
        resp = client.post("/chat", json={"query": "What is the GPU driver version?"})
        assert resp.status_code == 200
        data = resp.json()
        # Must be handoff_recommended, never insufficient_evidence
        assert data["status"] == "handoff_recommended"


def test_chat_unexpected_exception_returns_safe_500(client):
    """Verify unhandled exceptions return 500 without leaking stack traces or credentials."""
    with patch("api.routes.chat.answer_question", side_effect=RuntimeError("Secret database error")):
        resp = client.post("/chat", json={"query": "Any query"})
        assert resp.status_code == 500
        data = resp.json()
        assert data["detail"] == "An internal server error occurred while processing the request."
        # Verify secret internal error string is NOT leaked
        assert "Secret database error" not in resp.text


# ---------------------------------------------------------------------------
# CORS Configuration Tests
# ---------------------------------------------------------------------------


def test_cors_allowed_development_origin(client):
    """Verify allowed development origins receive Access-Control-Allow-Origin header."""
    headers = {
        "Origin": "http://localhost:3000",
        "Access-Control-Request-Method": "POST",
    }
    resp = client.options("/chat", headers=headers)
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_cors_disallowed_origin(client):
    """Verify disallowed origins do not receive Access-Control-Allow-Origin header."""
    headers = {
        "Origin": "http://malicious-site.com",
        "Access-Control-Request-Method": "POST",
    }
    resp = client.options("/chat", headers=headers)
    assert resp.headers.get("access-control-allow-origin") != "http://malicious-site.com"
