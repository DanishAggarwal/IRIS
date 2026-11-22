"""Unit and integration tests for Phase 3 Approved Document Download and Automatic Ingestion."""

from datetime import datetime, timezone
import hashlib
from pathlib import Path
from unittest.mock import MagicMock, patch
import uuid
import pytest
from fastapi.testclient import TestClient
import httpx
import pymupdf

from api.config import get_api_settings
from api.dependencies import get_current_user, get_database_session
from api.main import create_application
from crawler.acquisition import (
    acquire_and_ingest_document,
    download_and_validate_pdf,
    sanitize_pdf_filename,
    verify_local_pdf,
    recover_stale_ingestions_on_startup,
    _ACTIVE_INGESTIONS,
    _ACTIVE_INGESTIONS_LOCK,
    _PIPELINE_LOCK,
    MAX_DOWNLOAD_SIZE_BYTES,
)
from crawler.catalog import approve_document, seed_default_sources, upsert_discovered_documents
from crawler.config import DiscoveredItem
from database.connection import SessionLocal
from database.models import DiscoveredDocument, Document, DocumentApprovalAudit, DocumentChunk, Page, User


def create_minimal_pdf_bytes(content: str = "PEC Academic Syllabus 2026. Approved by Senate.") -> bytes:
    """Generate minimal valid PDF bytes with PyMuPDF."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 72), content)
    b = doc.tobytes()
    doc.close()
    return b


@pytest.fixture
def db_session():
    """Provides a transactional database session."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def admin_user(db_session):
    """Provides an authenticated admin user matching default admin config."""
    settings = get_api_settings()
    admin_email = settings.admin_emails_list[0] if settings.admin_emails_list else "admin@pec.edu.in"
    user = db_session.query(User).filter_by(email=admin_email).first()
    if not user:
        user = User(
            id=uuid.uuid4(),
            google_sub="google_sub_admin_p3",
            email=admin_email,
            name="Admin User",
            role="admin",
            is_active=True,
        )
        db_session.add(user)
        db_session.commit()
    return user


@pytest.fixture
def non_admin_user(db_session):
    """Provides an authenticated regular student user."""
    user = db_session.query(User).filter_by(email="student.p3@pec.edu.in").first()
    if not user:
        user = User(
            id=uuid.uuid4(),
            google_sub="google_sub_student_p3",
            email="student.p3@pec.edu.in",
            name="Student User",
            role="user",
            is_active=True,
        )
        db_session.add(user)
        db_session.commit()
    return user


@pytest.fixture
def sample_approved_doc(db_session, admin_user):
    """Provides a seeded discovered document in 'approved' status."""
    seed_default_sources(db_session)
    item = DiscoveredItem(
        title="B.Tech Computer Science Scheme 2026",
        source_page_url="https://pec.ac.in/programmes/ug/structure",
        download_url="https://pec.ac.in/sites/default/files/cse_scheme_2026.pdf",
        category="UG Curriculum",
    )
    upsert_discovered_documents(db_session, "ug-structure", [item])
    doc = db_session.query(DiscoveredDocument).filter_by(download_url=item.download_url).first()
    approve_document(db_session, doc.id, admin_user)
    db_session.refresh(doc)
    return doc


# ---------------------------------------------------------------------------
# 1. Download & Validation Tests
# ---------------------------------------------------------------------------


def test_download_and_validate_pdf_success():
    """Verify download_and_validate_pdf succeeds for valid PDF stream."""
    pdf_bytes = create_minimal_pdf_bytes("Valid Course Curriculum")
    expected_hash = hashlib.sha256(pdf_bytes).hexdigest()

    mock_client = MagicMock(spec=httpx.Client)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.history = []
    mock_resp.url = httpx.URL("https://pec.ac.in/sites/default/files/valid.pdf")
    mock_resp.headers = {"Content-Length": str(len(pdf_bytes))}
    mock_resp.iter_bytes.return_value = [pdf_bytes]
    mock_client.stream.return_value.__enter__.return_value = mock_resp

    temp_path, sha256, size = download_and_validate_pdf(
        url="https://pec.ac.in/sites/default/files/valid.pdf",
        client=mock_client,
    )

    try:
        assert temp_path.exists()
        assert sha256 == expected_hash
        assert size == len(pdf_bytes)
    finally:
        temp_path.unlink(missing_ok=True)


def test_download_rejects_external_origin():
    """Attempting to download from outside allowed PEC domains must raise ValueError immediately."""
    with pytest.raises(ValueError, match="outside authorized PEC domains"):
        download_and_validate_pdf("https://malicious-external-site.com/doc.pdf")


def test_download_rejects_redirect_to_external_origin():
    """Redirects to an external domain must be blocked with a security error."""
    mock_client = MagicMock(spec=httpx.Client)
    mock_resp = MagicMock()
    mock_resp.status_code = 200

    hop1 = MagicMock()
    hop1.url = httpx.URL("https://pec.ac.in/redirect")

    hop2 = MagicMock()
    hop2.url = httpx.URL("https://attacker.com/malicious.pdf")

    mock_resp.history = [hop1, hop2]
    mock_resp.url = hop2.url
    mock_client.stream.return_value.__enter__.return_value = mock_resp

    with pytest.raises(ValueError, match="Redirect hop .* points outside authorized PEC domains"):
        download_and_validate_pdf(
            url="https://pec.ac.in/sites/default/files/doc.pdf",
            client=mock_client,
        )


def test_download_rejects_invalid_magic_header():
    """Content lacking %PDF- magic bytes must be rejected as invalid document format."""
    html_bytes = b"<!DOCTYPE html><html><body>Error 404 Not Found</body></html>"

    mock_client = MagicMock(spec=httpx.Client)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.history = []
    mock_resp.url = httpx.URL("https://pec.ac.in/sites/default/files/fake.pdf")
    mock_resp.headers = {"Content-Length": str(len(html_bytes))}
    mock_resp.iter_bytes.return_value = [html_bytes]
    mock_client.stream.return_value.__enter__.return_value = mock_resp

    with pytest.raises(ValueError, match="Invalid document format: expected PDF magic header"):
        download_and_validate_pdf(
            url="https://pec.ac.in/sites/default/files/fake.pdf",
            client=mock_client,
        )


def test_download_rejects_corrupted_pdf_structure():
    """Bytes with %PDF- header but corrupt structural content must fail PyMuPDF validation."""
    corrupt_bytes = b"%PDF-1.4 corrupt junk payload that is not a valid cross-reference table"

    mock_client = MagicMock(spec=httpx.Client)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.history = []
    mock_resp.url = httpx.URL("https://pec.ac.in/sites/default/files/corrupt.pdf")
    mock_resp.headers = {"Content-Length": str(len(corrupt_bytes))}
    mock_resp.iter_bytes.return_value = [corrupt_bytes]
    mock_client.stream.return_value.__enter__.return_value = mock_resp

    with pytest.raises(ValueError, match="Corrupt or unreadable PDF document"):
        download_and_validate_pdf(
            url="https://pec.ac.in/sites/default/files/corrupt.pdf",
            client=mock_client,
        )


def test_download_rejects_oversized_content():
    """Files exceeding maximum allowed download size must be aborted."""
    mock_client = MagicMock(spec=httpx.Client)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.history = []
    mock_resp.url = httpx.URL("https://pec.ac.in/sites/default/files/huge.pdf")
    mock_resp.headers = {"Content-Length": str(MAX_DOWNLOAD_SIZE_BYTES + 1000)}
    mock_client.stream.return_value.__enter__.return_value = mock_resp

    with pytest.raises(ValueError, match="exceeds maximum limit"):
        download_and_validate_pdf(
            url="https://pec.ac.in/sites/default/files/huge.pdf",
            client=mock_client,
        )


def test_download_handles_http_errors():
    """Non-200 responses (e.g. 404, 500) raise RuntimeError."""
    mock_client = MagicMock(spec=httpx.Client)
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_client.stream.return_value.__enter__.return_value = mock_resp

    with pytest.raises(RuntimeError, match="HTTP 404"):
        download_and_validate_pdf(
            url="https://pec.ac.in/sites/default/files/missing.pdf",
            client=mock_client,
        )


def test_sanitize_pdf_filename():
    """Verify filename sanitization produces clean, collision-safe names."""
    assert sanitize_pdf_filename("UG Curriculum 2023 Vol 2.0", "") == "UG_Curriculum_2023_Vol_2_0.pdf"
    assert sanitize_pdf_filename("Minutes of 109th Meeting held on 14.05.2025", "") == "Minutes_of_109th_Meeting_held_on_14_05_2025.pdf"
    assert sanitize_pdf_filename("", "https://pec.ac.in/files/document.pdf") == "document.pdf"


# ---------------------------------------------------------------------------
# 2. Ingestion & Duplicate Handling Tests
# ---------------------------------------------------------------------------


def test_cannot_ingest_unapproved_document(db_session, admin_user):
    """Documents in 'discovered' or 'rejected' status must be rejected with 400."""
    item = DiscoveredItem(
        title="Unapproved Draft Policy",
        source_page_url="https://pec.ac.in/draft",
        download_url="https://pec.ac.in/files/draft_policy.pdf",
        category="Policy",
    )
    upsert_discovered_documents(db_session, "tnp-policy", [item])
    doc = db_session.query(DiscoveredDocument).filter_by(download_url=item.download_url).first()
    assert doc.status == "discovered"

    app = create_application()
    app.dependency_overrides[get_database_session] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: admin_user

    with TestClient(app) as client:
        resp = client.post(f"/admin/crawler/documents/{doc.id}/ingest")
        assert resp.status_code == 400
        assert "Only approved documents" in resp.json()["detail"]

    # Cleanup
    db_session.delete(doc)
    db_session.commit()


def test_duplicate_sha256_links_existing_document(db_session, admin_user, sample_approved_doc, tmp_path):
    """When downloaded document SHA-256 matches an already ingested IRIS document, link it without re-ingesting."""
    # 1. Create a dummy existing Document in PostgreSQL
    pdf_bytes = create_minimal_pdf_bytes("Existing Institutional Content")
    sha256 = hashlib.sha256(pdf_bytes).hexdigest()

    existing_doc = Document(
        id=uuid.uuid4(),
        filename="existing_handbook.pdf",
        sha256=sha256,
        status="complete",
        page_count=1,
    )
    db_session.add(existing_doc)
    db_session.commit()

    # Mock download to return identical bytes
    mock_client = MagicMock(spec=httpx.Client)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.history = []
    mock_resp.url = httpx.URL(sample_approved_doc.download_url)
    mock_resp.headers = {"Content-Length": str(len(pdf_bytes))}
    mock_resp.iter_bytes.return_value = [pdf_bytes]
    mock_client.stream.return_value.__enter__.return_value = mock_resp

    updated_doc = acquire_and_ingest_document(
        document_id=sample_approved_doc.id,
        admin_user=admin_user,
        documents_dir=tmp_path,
        http_client=mock_client,
    )

    assert updated_doc.status == "ingested"
    assert updated_doc.sha256 == sha256
    assert updated_doc.ingested_document_id == existing_doc.id
    assert updated_doc.local_filename == "existing_handbook.pdf"
    assert updated_doc.error_message is None

    # Verify audit record reflects duplicate link
    audit = db_session.query(DocumentApprovalAudit).filter_by(document_id=updated_doc.id).order_by(DocumentApprovalAudit.created_at.desc()).first()
    assert audit.action == "ingest_completed"
    assert "duplicate matched" in audit.reason.lower()

    # Cleanup
    db_session.delete(existing_doc)
    db_session.commit()


def test_successful_handoff_to_ingestion_pipeline(db_session, admin_user, sample_approved_doc, tmp_path):
    """Verify end-to-end acquisition, duplicate check, pipeline execution, and database verification."""
    pdf_bytes = create_minimal_pdf_bytes("New Approved Regulation 2026. Academic Senate Approved.")
    sha256 = hashlib.sha256(pdf_bytes).hexdigest()

    mock_client = MagicMock(spec=httpx.Client)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.history = []
    mock_resp.url = httpx.URL(sample_approved_doc.download_url)
    mock_resp.headers = {"Content-Length": str(len(pdf_bytes))}
    mock_resp.iter_bytes.return_value = [pdf_bytes]
    mock_client.stream.return_value.__enter__.return_value = mock_resp

    # Mock run_full_pipeline so it simulates pipeline creation of Document and chunks
    created_doc_id = uuid.uuid4()

    def mock_pipeline_runner(force=False, skip_embeddings=False):
        # Simulate pipeline inserting completed document and chunks into DB
        with SessionLocal() as s:
            d = Document(
                id=created_doc_id,
                filename="B_Tech_Computer_Science_Scheme_2026.pdf",
                sha256=sha256,
                status="complete",
                page_count=1,
            )
            s.add(d)
            s.commit()
            c = DocumentChunk(
                id=uuid.uuid4(),
                document_id=d.id,
                chunk_index=0,
                chunk_text="New Approved Regulation 2026.",
                start_page=1,
                end_page=1,
                char_count=30,
                token_count=10,
                chunking_version="v1.0",
                embedding=[0.0] * 768,
                embedding_model="text-embedding-004",
            )
            s.add(c)
            s.commit()
        return 0

    with patch("crawler.acquisition.run_full_pipeline", side_effect=mock_pipeline_runner):
        updated_doc = acquire_and_ingest_document(
            document_id=sample_approved_doc.id,
            admin_user=admin_user,
            documents_dir=tmp_path,
            http_client=mock_client,
        )

    assert updated_doc.status == "ingested"
    assert updated_doc.sha256 == sha256
    assert updated_doc.ingested_document_id == created_doc_id
    assert updated_doc.local_filename is not None
    assert updated_doc.ingested_at is not None
    assert updated_doc.error_message is None

    # Verify file was placed into documents_dir
    placed_file = tmp_path / updated_doc.local_filename
    assert placed_file.exists()

    # Cleanup simulated records
    with SessionLocal() as s:
        s.query(DocumentChunk).filter_by(document_id=created_doc_id).delete()
        s.query(Document).filter_by(id=created_doc_id).delete()
        s.commit()


def test_download_failure_and_retry(db_session, admin_user, sample_approved_doc, tmp_path):
    """Verify download network failure sets download_failed and allows retry."""
    # First attempt: download raises ConnectionError
    mock_client_fail = MagicMock(spec=httpx.Client)
    mock_client_fail.stream.side_effect = httpx.ConnectError("Network connection reset")

    updated_doc = acquire_and_ingest_document(
        document_id=sample_approved_doc.id,
        admin_user=admin_user,
        documents_dir=tmp_path,
        http_client=mock_client_fail,
    )
    assert updated_doc.status == "download_failed"
    assert "Network connection reset" in updated_doc.error_message

    # Second attempt (Retry): succeeds
    pdf_bytes = create_minimal_pdf_bytes("Retry Success Document")
    sha256 = hashlib.sha256(pdf_bytes).hexdigest()

    mock_client_ok = MagicMock(spec=httpx.Client)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.history = []
    mock_resp.url = httpx.URL(sample_approved_doc.download_url)
    mock_resp.headers = {"Content-Length": str(len(pdf_bytes))}
    mock_resp.iter_bytes.return_value = [pdf_bytes]
    mock_client_ok.stream.return_value.__enter__.return_value = mock_resp

    created_doc_id = uuid.uuid4()

    def mock_pipeline_runner(force=False, skip_embeddings=False):
        with SessionLocal() as s:
            d = Document(id=created_doc_id, filename="retry_doc.pdf", sha256=sha256, status="complete", page_count=1)
            s.add(d)
            s.commit()
            c = DocumentChunk(
                id=uuid.uuid4(),
                document_id=d.id,
                chunk_index=0,
                chunk_text="Retry Success.",
                start_page=1,
                end_page=1,
                char_count=15,
                token_count=5,
                chunking_version="v1.0",
                embedding=[0.1] * 768,
            )
            s.add(c)
            s.commit()
        return 0

    with patch("crawler.acquisition.run_full_pipeline", side_effect=mock_pipeline_runner):
        retried_doc = acquire_and_ingest_document(
            document_id=sample_approved_doc.id,
            admin_user=admin_user,
            documents_dir=tmp_path,
            http_client=mock_client_ok,
        )

    assert retried_doc.status == "ingested"
    assert retried_doc.error_message is None

    # Cleanup
    with SessionLocal() as s:
        s.query(DocumentChunk).filter_by(document_id=created_doc_id).delete()
        s.query(Document).filter_by(id=created_doc_id).delete()
        s.commit()


# ---------------------------------------------------------------------------
# 3. Security & Admin API Endpoints Tests
# ---------------------------------------------------------------------------


def test_non_admin_cannot_access_ingestion_endpoints(db_session, non_admin_user, sample_approved_doc):
    """Non-administrators must receive HTTP 403 Forbidden on ingestion and retry endpoints."""
    app = create_application()
    app.dependency_overrides[get_database_session] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: non_admin_user

    with TestClient(app) as client:
        # 1. Ingest
        resp_ingest = client.post(f"/admin/crawler/documents/{sample_approved_doc.id}/ingest")
        assert resp_ingest.status_code == 403

        # 2. Retry
        resp_retry = client.post(f"/admin/crawler/documents/{sample_approved_doc.id}/retry")
        assert resp_retry.status_code == 403

        # 3. Status
        resp_status = client.get(f"/admin/crawler/documents/{sample_approved_doc.id}/ingestion-status")
        assert resp_status.status_code == 403


def test_api_ingestion_and_status_endpoints(db_session, admin_user, sample_approved_doc):
    """Admin triggering ingestion returns updated document with downloading status and status endpoint works."""
    app = create_application()
    app.dependency_overrides[get_database_session] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: admin_user

    with patch("crawler.acquisition.acquire_and_ingest_document") as mock_acquire:
        mock_acquire.return_value = sample_approved_doc

        with TestClient(app) as client:
            resp = client.post(f"/admin/crawler/documents/{sample_approved_doc.id}/ingest")
            assert resp.status_code == 200
            data = resp.json()
            assert data["id"] == str(sample_approved_doc.id)

            # Check ingestion-status endpoint
            resp_st = client.get(f"/admin/crawler/documents/{sample_approved_doc.id}/ingestion-status")
            assert resp_st.status_code == 200
            st_data = resp_st.json()
            assert st_data["id"] == str(sample_approved_doc.id)
            assert "download_url" in st_data


# ---------------------------------------------------------------------------
# 4. Phase 3.1 Reliability Hardening Tests
# ---------------------------------------------------------------------------


def test_concurrent_ingestion_same_document_blocked(db_session, admin_user, sample_approved_doc):
    """Attempting simultaneous acquisition of the same document must raise RuntimeError or 409 Conflict."""
    app = create_application()
    app.dependency_overrides[get_database_session] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: admin_user

    with TestClient(app) as client:
        # 1. API level: if document status is already downloading, reject with 409
        sample_approved_doc.status = "downloading"
        db_session.commit()

        resp = client.post(f"/admin/crawler/documents/{sample_approved_doc.id}/ingest")
        assert resp.status_code == 409
        assert "already in progress" in resp.json()["detail"]

    # 2. Worker level: if document_id is in _ACTIVE_INGESTIONS, raise RuntimeError
    with _ACTIVE_INGESTIONS_LOCK:
        _ACTIVE_INGESTIONS.add(sample_approved_doc.id)

    try:
        with pytest.raises(RuntimeError, match="already in progress"):
            acquire_and_ingest_document(
                document_id=sample_approved_doc.id,
                admin_user=admin_user,
            )
    finally:
        with _ACTIVE_INGESTIONS_LOCK:
            _ACTIVE_INGESTIONS.discard(sample_approved_doc.id)


def test_pipeline_serialization_across_different_documents(db_session, admin_user, tmp_path):
    """The global ingestion pipeline must be protected by _PIPELINE_LOCK during acquisition."""
    pdf_bytes = create_minimal_pdf_bytes("Serialized Pipeline Test Document")
    sha256 = hashlib.sha256(pdf_bytes).hexdigest()

    item = DiscoveredItem(
        title="Serialized Document 1",
        source_page_url="https://pec.ac.in/serial1",
        download_url="https://pec.ac.in/files/serial1.pdf",
        category="Curriculum",
    )
    upsert_discovered_documents(db_session, "ug-structure", [item])
    doc1 = db_session.query(DiscoveredDocument).filter_by(download_url=item.download_url).first()
    doc1.status = "approved"
    db_session.commit()

    mock_client = MagicMock(spec=httpx.Client)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.history = []
    mock_resp.url = httpx.URL(doc1.download_url)
    mock_resp.headers = {"Content-Length": str(len(pdf_bytes))}
    mock_resp.iter_bytes.return_value = [pdf_bytes]
    mock_client.stream.return_value.__enter__.return_value = mock_resp

    pipeline_was_locked = False

    def check_lock(*args, **kwargs):
        nonlocal pipeline_was_locked
        pipeline_was_locked = _PIPELINE_LOCK.locked()
        with SessionLocal() as s:
            d = Document(
                id=uuid.uuid4(),
                filename=f"{doc1.title}.pdf",
                sha256=sha256,
                status="complete",
                page_count=1,
            )
            s.add(d)
            s.commit()
            c = DocumentChunk(
                id=uuid.uuid4(),
                document_id=d.id,
                chunk_index=0,
                chunk_text="Dummy chunk",
                start_page=1,
                end_page=1,
                char_count=11,
                token_count=2,
                chunking_version="1.0",
            )
            s.add(c)
            s.commit()
        return 0

    with patch("crawler.acquisition.run_full_pipeline", side_effect=check_lock):
        res = acquire_and_ingest_document(
            document_id=doc1.id,
            admin_user=admin_user,
            documents_dir=tmp_path,
            http_client=mock_client,
        )

    assert pipeline_was_locked is True
    assert res.status == "ingested"
    assert not _PIPELINE_LOCK.locked()
    assert doc1.id not in _ACTIVE_INGESTIONS


def test_lock_release_after_success_and_failure(db_session, admin_user, tmp_path):
    """Lock must be cleanly released whether acquisition succeeds or fails."""
    item = DiscoveredItem(
        title="Failing Document Lock Test",
        source_page_url="https://pec.ac.in/fail_lock",
        download_url="https://pec.ac.in/files/fail_lock.pdf",
        category="Curriculum",
    )
    upsert_discovered_documents(db_session, "ug-structure", [item])
    doc = db_session.query(DiscoveredDocument).filter_by(download_url=item.download_url).first()
    doc.status = "approved"
    db_session.commit()

    mock_client = MagicMock(spec=httpx.Client)
    mock_client.stream.side_effect = RuntimeError("Connection timeout")

    res = acquire_and_ingest_document(
        document_id=doc.id,
        admin_user=admin_user,
        documents_dir=tmp_path,
        http_client=mock_client,
    )

    assert res.status == "download_failed"
    assert doc.id not in _ACTIVE_INGESTIONS
    assert not _PIPELINE_LOCK.locked()


def test_retry_reuses_existing_validated_local_pdf(db_session, admin_user, tmp_path):
    """Retry of an ingest_failed document reuses valid local PDF without calling download."""
    pdf_bytes = create_minimal_pdf_bytes("Local Cached PDF Content")
    sha256 = hashlib.sha256(pdf_bytes).hexdigest()

    local_name = "cached_doc.pdf"
    cached_file = tmp_path / local_name
    cached_file.write_bytes(pdf_bytes)

    item = DiscoveredItem(
        title="Cached Document",
        source_page_url="https://pec.ac.in/cached",
        download_url="https://pec.ac.in/files/cached.pdf",
        category="Rules",
    )
    upsert_discovered_documents(db_session, "rules-procedures", [item])
    doc = db_session.query(DiscoveredDocument).filter_by(download_url=item.download_url).first()
    doc.status = "ingest_failed"
    doc.local_filename = local_name
    doc.sha256 = sha256
    doc.error_message = "Previous pipeline run timed out"
    db_session.commit()

    mock_client = MagicMock(spec=httpx.Client)

    def fake_pipeline(*args, **kwargs):
        with SessionLocal() as s:
            d = Document(
                id=uuid.uuid4(),
                filename=local_name,
                sha256=sha256,
                status="complete",
                page_count=1,
            )
            s.add(d)
            s.commit()
            c = DocumentChunk(
                id=uuid.uuid4(),
                document_id=d.id,
                chunk_index=0,
                chunk_text="Cached chunk text",
                start_page=1,
                end_page=1,
                char_count=17,
                token_count=3,
                chunking_version="1.0",
            )
            s.add(c)
            s.commit()
        return 0

    with patch("crawler.acquisition.download_and_validate_pdf") as mock_dl, \
         patch("crawler.acquisition.run_full_pipeline", side_effect=fake_pipeline):
        res = acquire_and_ingest_document(
            document_id=doc.id,
            admin_user=admin_user,
            documents_dir=tmp_path,
            http_client=mock_client,
        )

        mock_dl.assert_not_called()

    assert res.status == "ingested"
    assert res.error_message is None

    # Verify audit trail has ingest_resumed
    audits = db_session.query(DocumentApprovalAudit).filter_by(document_id=doc.id).all()
    actions = [a.action for a in audits]
    assert "ingest_resumed" in actions


def test_retry_downloads_again_when_local_file_missing(db_session, admin_user, tmp_path):
    """Retry downloads freshly when local_filename does not exist on disk."""
    pdf_bytes = create_minimal_pdf_bytes("Fresh Download On Missing Local")
    sha256 = hashlib.sha256(pdf_bytes).hexdigest()

    item = DiscoveredItem(
        title="Missing Local File Doc",
        source_page_url="https://pec.ac.in/missing",
        download_url="https://pec.ac.in/files/missing.pdf",
        category="Rules",
    )
    upsert_discovered_documents(db_session, "rules-procedures", [item])
    doc = db_session.query(DiscoveredDocument).filter_by(download_url=item.download_url).first()
    doc.status = "ingest_failed"
    doc.local_filename = "non_existent_file.pdf"
    doc.sha256 = sha256
    db_session.commit()

    mock_client = MagicMock(spec=httpx.Client)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.history = []
    mock_resp.url = httpx.URL(doc.download_url)
    mock_resp.headers = {"Content-Length": str(len(pdf_bytes))}
    mock_resp.iter_bytes.return_value = [pdf_bytes]
    mock_client.stream.return_value.__enter__.return_value = mock_resp

    def fake_pipeline(*args, **kwargs):
        with SessionLocal() as s:
            d = Document(
                id=uuid.uuid4(),
                filename="Missing_Local_File_Doc.pdf",
                sha256=sha256,
                status="complete",
                page_count=1,
            )
            s.add(d)
            s.commit()
            c = DocumentChunk(
                id=uuid.uuid4(),
                document_id=d.id,
                chunk_index=0,
                chunk_text="Fresh chunk",
                start_page=1,
                end_page=1,
                char_count=11,
                token_count=2,
                chunking_version="1.0",
            )
            s.add(c)
            s.commit()
        return 0

    with patch("crawler.acquisition.download_and_validate_pdf", wraps=download_and_validate_pdf) as spy_dl, \
         patch("crawler.acquisition.run_full_pipeline", side_effect=fake_pipeline):
        res = acquire_and_ingest_document(
            document_id=doc.id,
            admin_user=admin_user,
            documents_dir=tmp_path,
            http_client=mock_client,
        )

        assert spy_dl.call_count == 1

    assert res.status == "ingested"


def test_retry_rejects_and_redownloads_invalid_or_mismatched_local_file(db_session, admin_user, tmp_path):
    """Local file with corrupted content or hash mismatch is rejected and re-downloaded."""
    corrupted_file = tmp_path / "corrupted.pdf"
    corrupted_file.write_bytes(b"CORRUPTED_NON_PDF_DATA")

    valid_pdf_bytes = create_minimal_pdf_bytes("Valid Download Replacement")
    valid_sha256 = hashlib.sha256(valid_pdf_bytes).hexdigest()

    item = DiscoveredItem(
        title="Corrupted Local Doc",
        source_page_url="https://pec.ac.in/corrupt_local",
        download_url="https://pec.ac.in/files/corrupt_local.pdf",
        category="Rules",
    )
    upsert_discovered_documents(db_session, "rules-procedures", [item])
    doc = db_session.query(DiscoveredDocument).filter_by(download_url=item.download_url).first()
    doc.status = "ingest_failed"
    doc.local_filename = "corrupted.pdf"
    doc.sha256 = "expected_original_hash_1234"
    db_session.commit()

    is_valid, _, reason = verify_local_pdf(corrupted_file, expected_sha256=doc.sha256)
    assert is_valid is False

    mock_client = MagicMock(spec=httpx.Client)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.history = []
    mock_resp.url = httpx.URL(doc.download_url)
    mock_resp.headers = {"Content-Length": str(len(valid_pdf_bytes))}
    mock_resp.iter_bytes.return_value = [valid_pdf_bytes]
    mock_client.stream.return_value.__enter__.return_value = mock_resp

    def fake_pipeline(*args, **kwargs):
        with SessionLocal() as s:
            d = Document(
                id=uuid.uuid4(),
                filename="Corrupted_Local_Doc.pdf",
                sha256=valid_sha256,
                status="complete",
                page_count=1,
            )
            s.add(d)
            s.commit()
            c = DocumentChunk(
                id=uuid.uuid4(),
                document_id=d.id,
                chunk_index=0,
                chunk_text="Re-downloaded chunk",
                start_page=1,
                end_page=1,
                char_count=19,
                token_count=3,
                chunking_version="1.0",
            )
            s.add(c)
            s.commit()
        return 0

    with patch("crawler.acquisition.download_and_validate_pdf", wraps=download_and_validate_pdf) as spy_dl, \
         patch("crawler.acquisition.run_full_pipeline", side_effect=fake_pipeline):
        res = acquire_and_ingest_document(
            document_id=doc.id,
            admin_user=admin_user,
            documents_dir=tmp_path,
            http_client=mock_client,
        )

        assert spy_dl.call_count == 1

    assert res.status == "ingested"
    assert res.sha256 == valid_sha256


def test_successful_ingestion_updates_change_status(db_session, admin_user, tmp_path):
    """Successful ingestion resets change_status to 'unchanged'."""
    pdf_bytes = create_minimal_pdf_bytes("Updated Version of Rules")
    sha256 = hashlib.sha256(pdf_bytes).hexdigest()

    item = DiscoveredItem(
        title="Updated Rules 2026",
        source_page_url="https://pec.ac.in/updated_rules",
        download_url="https://pec.ac.in/files/updated_rules.pdf",
        category="Rules",
    )
    upsert_discovered_documents(db_session, "rules-procedures", [item])
    doc = db_session.query(DiscoveredDocument).filter_by(download_url=item.download_url).first()
    doc.status = "approved"
    doc.change_status = "potentially_changed"
    db_session.commit()

    mock_client = MagicMock(spec=httpx.Client)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.history = []
    mock_resp.url = httpx.URL(doc.download_url)
    mock_resp.headers = {"Content-Length": str(len(pdf_bytes))}
    mock_resp.iter_bytes.return_value = [pdf_bytes]
    mock_client.stream.return_value.__enter__.return_value = mock_resp

    def fake_pipeline(*args, **kwargs):
        with SessionLocal() as s:
            d = Document(
                id=uuid.uuid4(),
                filename="Updated_Rules_2026.pdf",
                sha256=sha256,
                status="complete",
                page_count=1,
            )
            s.add(d)
            s.commit()
            c = DocumentChunk(
                id=uuid.uuid4(),
                document_id=d.id,
                chunk_index=0,
                chunk_text="Rules chunk text",
                start_page=1,
                end_page=1,
                char_count=16,
                token_count=3,
                chunking_version="1.0",
            )
            s.add(c)
            s.commit()
        return 0

    with patch("crawler.acquisition.run_full_pipeline", side_effect=fake_pipeline):
        res = acquire_and_ingest_document(
            document_id=doc.id,
            admin_user=admin_user,
            documents_dir=tmp_path,
            http_client=mock_client,
        )

    assert res.status == "ingested"
    assert res.change_status == "unchanged"


def test_startup_recovery_interrupted_downloading_and_ingesting(db_session):
    """Startup recovery cleans interrupted downloading and ingesting records without touching finished ones."""
    # Clear any leftover records from other test fixtures
    recover_stale_ingestions_on_startup(db_session)

    uid = uuid.uuid4().hex[:6]
    item1 = DiscoveredItem(
        title=f"Interrupted Download Doc {uid}",
        source_page_url=f"https://pec.ac.in/i1_{uid}",
        download_url=f"https://pec.ac.in/files/i1_{uid}.pdf",
        category="Rules",
    )
    item2 = DiscoveredItem(
        title=f"Interrupted Ingest Doc {uid}",
        source_page_url=f"https://pec.ac.in/i2_{uid}",
        download_url=f"https://pec.ac.in/files/i2_{uid}.pdf",
        category="Rules",
    )
    item3 = DiscoveredItem(
        title=f"Normal Ingested Doc {uid}",
        source_page_url=f"https://pec.ac.in/i3_{uid}",
        download_url=f"https://pec.ac.in/files/i3_{uid}.pdf",
        category="Rules",
    )
    upsert_discovered_documents(db_session, "rules-procedures", [item1, item2, item3])

    doc1 = db_session.query(DiscoveredDocument).filter_by(download_url=item1.download_url).first()
    doc1.status = "downloading"

    doc2 = db_session.query(DiscoveredDocument).filter_by(download_url=item2.download_url).first()
    doc2.status = "ingesting"
    doc2.local_filename = "saved_file.pdf"

    doc3 = db_session.query(DiscoveredDocument).filter_by(download_url=item3.download_url).first()
    doc3.status = "ingested"

    db_session.commit()

    recovered_count = recover_stale_ingestions_on_startup(db_session)
    assert recovered_count == 2

    db_session.refresh(doc1)
    db_session.refresh(doc2)
    db_session.refresh(doc3)

    assert doc1.status == "download_failed"
    assert "Download interrupted by application restart" in doc1.error_message

    assert doc2.status == "ingest_failed"
    assert "Ingestion interrupted by application restart" in doc2.error_message
    assert doc2.local_filename == "saved_file.pdf"

    assert doc3.status == "ingested"


def test_discovery_and_approval_alone_never_trigger_acquisition(db_session, admin_user):
    """Discovery and approval alone must never trigger downloads or acquisition."""
    uid = uuid.uuid4().hex[:6]
    item = DiscoveredItem(
        title=f"Passive Discovery Policy {uid}",
        source_page_url=f"https://pec.ac.in/passive_{uid}",
        download_url=f"https://pec.ac.in/files/passive_policy_{uid}.pdf",
        category="Policy",
    )

    with patch("crawler.acquisition.download_and_validate_pdf") as mock_dl, \
         patch("crawler.acquisition.acquire_and_ingest_document") as mock_acquire:
        upsert_discovered_documents(db_session, "tnp-policy", [item])
        doc = db_session.query(DiscoveredDocument).filter_by(download_url=item.download_url).first()
        assert doc.status == "discovered"

        approved_doc = approve_document(db_session, doc.id, admin_user)
        assert approved_doc.status == "approved"

        mock_dl.assert_not_called()
        mock_acquire.assert_not_called()
