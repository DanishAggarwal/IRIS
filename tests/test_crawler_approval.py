"""Comprehensive tests for Phase 2 Document Catalogue, Change Detection, and Approval Backend."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
import uuid
import pytest
from fastapi.testclient import TestClient

from api.config import get_api_settings
from api.dependencies import get_current_user, get_database_session
from api.main import create_application
from crawler.catalog import (
    approve_document,
    get_all_sources,
    get_catalog_stats,
    get_discovered_document_by_id,
    reconsider_document,
    reject_document,
    seed_default_sources,
    start_scan_execution,
    upsert_discovered_documents,
)
from crawler.config import DiscoveredItem
from database.connection import SessionLocal
from database.models import (
    CrawlerScan,
    CrawlerSource,
    DiscoveredDocument,
    DocumentApprovalAudit,
    User,
)


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
            google_sub="google_sub_admin_123",
            email=admin_email,
            name="Admin User",
            role="admin",
            is_active=True,
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)
    return user


@pytest.fixture
def student_user(db_session):
    """Provides an authenticated non-admin student user."""
    user = db_session.query(User).filter_by(email="student.sid@pec.edu.in").first()
    if not user:
        user = User(
            id=uuid.uuid4(),
            google_sub="google_sub_student_456",
            email="student.sid@pec.edu.in",
            name="Student User",
            role="user",
            is_active=True,
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)
    return user


@pytest.fixture
def sample_discovered_doc(db_session):
    """Inserts a clean sample discovered document for testing."""
    seed_default_sources(db_session)
    doc_id = uuid.uuid4()
    doc = DiscoveredDocument(
        id=doc_id,
        source_id="tnp-policy",
        title="Test Placement Policy 2026",
        source_page_url="https://pec.ac.in/tnp/policy",
        download_url=f"https://pec.ac.in/sites/files/test_policy_{doc_id}.pdf",
        category="Training & Placement",
        file_type="pdf",
        status="discovered",
        change_status="unknown",
        first_discovered_at=datetime.now(timezone.utc),
        last_discovered_at=datetime.now(timezone.utc),
        last_scanned_at=datetime.now(timezone.utc),
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)
    yield doc

    # Cleanup
    db_session.query(DocumentApprovalAudit).filter(
        DocumentApprovalAudit.document_id == doc_id
    ).delete(synchronize_session=False)
    db_session.query(DiscoveredDocument).filter(
        DiscoveredDocument.id == doc_id
    ).delete(synchronize_session=False)
    db_session.commit()


# ---------------------------------------------------------------------------
# 1. Authorization & Role Enforcement Tests
# ---------------------------------------------------------------------------


def test_admin_endpoints_require_authentication(db_session):
    """Unauthenticated requests must be rejected with 401."""
    app = create_application()
    app.dependency_overrides[get_database_session] = lambda: db_session
    with TestClient(app) as client:
        resp = client.get("/admin/crawler/documents")
        assert resp.status_code == 401
        resp_sources = client.get("/admin/crawler/sources")
        assert resp_sources.status_code == 401
        resp_scan = client.post("/admin/crawler/scan")
        assert resp_scan.status_code == 401


def test_non_admin_users_forbidden(db_session, student_user):
    """Non-admin student users must be rejected with 403 Forbidden."""
    app = create_application()
    app.dependency_overrides[get_database_session] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: student_user
    with TestClient(app) as client:
        resp = client.get("/admin/crawler/documents")
        assert resp.status_code == 403
        assert "Administrator privileges required" in resp.json()["detail"]

        resp_scan = client.post("/admin/crawler/scan")
        assert resp_scan.status_code == 403


# ---------------------------------------------------------------------------
# 2. Source Management Endpoints
# ---------------------------------------------------------------------------


def test_list_and_update_sources(db_session, admin_user):
    """Admin can list and toggle sources."""
    app = create_application()
    app.dependency_overrides[get_database_session] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: admin_user
    with TestClient(app) as client:
        # List sources
        resp = client.get("/admin/crawler/sources")
        assert resp.status_code == 200
        sources = resp.json()
        assert len(sources) >= 5
        src_ids = [s["source_id"] for s in sources]
        assert "senate-moms" in src_ids

        # Update source
        patch_resp = client.patch(
            "/admin/crawler/sources/tnp-policy",
            json={"enabled": False, "category": "Corporate Relations"},
        )
        assert patch_resp.status_code == 200
        data = patch_resp.json()
        assert data["enabled"] is False
        assert data["category"] == "Corporate Relations"

        # Re-enable source
        client.patch("/admin/crawler/sources/tnp-policy", json={"enabled": True})


# ---------------------------------------------------------------------------
# 3. Document Catalogue & Filtering
# ---------------------------------------------------------------------------


def test_list_documents_pagination_and_search(db_session, admin_user, sample_discovered_doc):
    """Verify document pagination, search in title, and status filtering."""
    app = create_application()
    app.dependency_overrides[get_database_session] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: admin_user
    with TestClient(app) as client:
        # Query list
        resp = client.get("/admin/crawler/documents?page=1&page_size=10")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        assert "stats" in data
        assert len(data["items"]) <= 10

        # Filter by search
        resp_search = client.get("/admin/crawler/documents?search=Placement+Policy")
        assert resp_search.status_code == 200
        search_data = resp_search.json()
        assert search_data["total"] >= 1
        assert any(sample_discovered_doc.title in d["title"] for d in search_data["items"])

        # Filter by status
        resp_status = client.get("/admin/crawler/documents?status=discovered")
        assert resp_status.status_code == 200
        assert resp_status.json()["total"] >= 1


def test_get_individual_document_detail(db_session, admin_user, sample_discovered_doc):
    """Verify detailed retrieval of an individual document record."""
    app = create_application()
    app.dependency_overrides[get_database_session] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: admin_user
    with TestClient(app) as client:
        resp = client.get(f"/admin/crawler/documents/{sample_discovered_doc.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == str(sample_discovered_doc.id)
        assert data["title"] == sample_discovered_doc.title
        assert data["download_url"] == sample_discovered_doc.download_url


# ---------------------------------------------------------------------------
# 4. Approval, Rejection, and Reconsideration Workflows
# ---------------------------------------------------------------------------


def test_approve_reject_reconsider_lifecycle_and_audit(db_session, admin_user, sample_discovered_doc):
    """Verify state transitions and immutable audit logging."""
    app = create_application()
    app.dependency_overrides[get_database_session] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: admin_user
    with TestClient(app) as client:
        doc_id = str(sample_discovered_doc.id)

        # 1. Approve
        resp_app = client.post(f"/admin/crawler/documents/{doc_id}/approve")
        assert resp_app.status_code == 200
        doc_data = resp_app.json()
        assert doc_data["status"] == "approved"
        assert doc_data["approved_by"] == admin_user.email
        assert doc_data["approved_at"] is not None

        # 2. Reject with reason
        resp_rej = client.post(
            f"/admin/crawler/documents/{doc_id}/reject",
            json={"reason": "Superseded by 2026 edition"},
        )
        assert resp_rej.status_code == 200
        doc_rej = resp_rej.json()
        assert doc_rej["status"] == "rejected"
        assert doc_rej["rejection_reason"] == "Superseded by 2026 edition"
        assert doc_rej["approved_by"] is None

        # 3. Reconsider
        resp_rec = client.post(f"/admin/crawler/documents/{doc_id}/reconsider")
        assert resp_rec.status_code == 200
        doc_rec = resp_rec.json()
        assert doc_rec["status"] == "discovered"
        assert doc_rec["rejection_reason"] is None

        # 4. Verify Audit History
        resp_hist = client.get(f"/admin/crawler/documents/{doc_id}/history")
        assert resp_hist.status_code == 200
        history = resp_hist.json()
        assert len(history) == 3
        actions = [h["action"] for h in history]
        assert actions == ["reconsider", "reject", "approve"]
        for h in history:
            assert h["admin_email"] == admin_user.email


# ---------------------------------------------------------------------------
# 5. Scan Execution & Concurrency Locking
# ---------------------------------------------------------------------------


def test_scan_trigger_and_concurrency_lock(db_session, admin_user):
    """Verify scan trigger returns 202 and prevents concurrent overlapping scans."""
    app = create_application()
    app.dependency_overrides[get_database_session] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: admin_user
    with TestClient(app) as client:
        # Trigger scan
        resp = client.post("/admin/crawler/scan", json={"source_id": "tnp-policy"})
        assert resp.status_code == 202
        scan_data = resp.json()
        scan_id = scan_data["id"]
        assert scan_data["status"] == "running"
        assert scan_data["initiated_by"] == admin_user.email

        # Insert active running scan to verify concurrency lock rejection
        active_scan = CrawlerScan(
            id=uuid.uuid4(),
            status="running",
            initiated_by="other_admin@pec.edu.in",
            started_at=datetime.now(timezone.utc),
        )
        db_session.add(active_scan)
        db_session.commit()

        # Concurrent trigger must return 409 Conflict
        resp_concurrent = client.post("/admin/crawler/scan", json={"source_id": "tnp-policy"})
        assert resp_concurrent.status_code == 409
        assert "already in progress" in resp_concurrent.json()["detail"]

        # Cleanup active scan row
        db_session.delete(active_scan)
        db_session.commit()


# ---------------------------------------------------------------------------
# 6. Change Detection & Scans Preserving Decisions (Issue 2)
# ---------------------------------------------------------------------------


def test_change_detection_preserves_lifecycle_and_provenance(db_session, admin_user, sample_discovered_doc):
    """Verify HTTP metadata changes set change_status='potentially_changed' WITHOUT overwriting status."""
    # 1. Ingested document change detection
    sample_discovered_doc.status = "ingested"
    sample_discovered_doc.sha256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    sample_discovered_doc.http_etag = '"v1-hash"'
    sample_discovered_doc.http_last_modified = "Mon, 01 Jan 2024 00:00:00 GMT"
    sample_discovered_doc.http_content_length = 50000
    db_session.commit()

    # Re-scan with identical headers -> unchanged
    item_same = DiscoveredItem(
        title=sample_discovered_doc.title,
        source_page_url=sample_discovered_doc.source_page_url,
        download_url=sample_discovered_doc.download_url,
        category=sample_discovered_doc.category,
        http_etag='"v1-hash"',
        http_last_modified="Mon, 01 Jan 2024 00:00:00 GMT",
        http_content_length=50000,
    )
    new_c, upd_c, changed_c = upsert_discovered_documents(db_session, "tnp-policy", [item_same])
    db_session.refresh(sample_discovered_doc)
    assert new_c == 0
    assert upd_c == 1
    assert changed_c == 0
    assert sample_discovered_doc.status == "ingested"
    assert sample_discovered_doc.change_status == "unchanged"
    assert sample_discovered_doc.sha256 == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

    # Re-scan with modified ETag -> change_status='potentially_changed', status remains 'ingested'
    item_changed = DiscoveredItem(
        title=sample_discovered_doc.title,
        source_page_url=sample_discovered_doc.source_page_url,
        download_url=sample_discovered_doc.download_url,
        category=sample_discovered_doc.category,
        http_etag='"v2-new-hash"',
        http_last_modified="Mon, 01 Jan 2024 00:00:00 GMT",
        http_content_length=50000,
    )
    new_c, upd_c, changed_c = upsert_discovered_documents(db_session, "tnp-policy", [item_changed])
    db_session.refresh(sample_discovered_doc)
    assert changed_c == 1
    assert sample_discovered_doc.status == "ingested"  # MUST NOT be overwritten!
    assert sample_discovered_doc.change_status == "potentially_changed"
    assert sample_discovered_doc.sha256 == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

    # Repeated scan with unchanged headers preserves potentially_changed or unchanged without wiping status
    new_c, upd_c, changed_c = upsert_discovered_documents(db_session, "tnp-policy", [item_changed])
    db_session.refresh(sample_discovered_doc)
    assert sample_discovered_doc.status == "ingested"

    # 2. Approved document change detection
    sample_discovered_doc.status = "approved"
    sample_discovered_doc.approved_by = admin_user.email
    db_session.commit()

    item_approved_change = DiscoveredItem(
        title=sample_discovered_doc.title,
        source_page_url=sample_discovered_doc.source_page_url,
        download_url=sample_discovered_doc.download_url,
        category=sample_discovered_doc.category,
        http_etag='"v3-new-hash"',
    )
    upsert_discovered_documents(db_session, "tnp-policy", [item_approved_change])
    db_session.refresh(sample_discovered_doc)
    assert sample_discovered_doc.status == "approved"  # Remains approved
    assert sample_discovered_doc.change_status == "potentially_changed"
    assert sample_discovered_doc.approved_by == admin_user.email

    # 3. Rejected document change detection
    sample_discovered_doc.status = "rejected"
    sample_discovered_doc.rejection_reason = "Outdated syllabus"
    db_session.commit()

    item_rejected_change = DiscoveredItem(
        title=sample_discovered_doc.title,
        source_page_url=sample_discovered_doc.source_page_url,
        download_url=sample_discovered_doc.download_url,
        category=sample_discovered_doc.category,
        http_etag='"v4-newer-hash"',
    )
    upsert_discovered_documents(db_session, "tnp-policy", [item_rejected_change])
    db_session.refresh(sample_discovered_doc)
    assert sample_discovered_doc.status == "rejected"  # Remains rejected
    assert sample_discovered_doc.change_status == "potentially_changed"
    assert sample_discovered_doc.rejection_reason == "Outdated syllabus"

    # 4. Missing metadata remains 'unknown', never 'potentially_changed'
    item_no_meta = DiscoveredItem(
        title="Brand New Link Without Headers",
        source_page_url="https://pec.ac.in/test",
        download_url="https://pec.ac.in/test/no_meta.pdf",
        category="Test",
    )
    upsert_discovered_documents(db_session, "tnp-policy", [item_no_meta])
    no_meta_doc = db_session.query(DiscoveredDocument).filter_by(download_url="https://pec.ac.in/test/no_meta.pdf").first()
    assert no_meta_doc is not None
    assert no_meta_doc.change_status == "unknown"

    # Cleanup
    db_session.delete(no_meta_doc)
    db_session.commit()


def test_repeated_scan_preserves_human_approval_decision(db_session, admin_user, sample_discovered_doc):
    """A crawler scan must never reset an approved or rejected document back to discovered."""
    approve_document(db_session, sample_discovered_doc.id, admin_user)
    db_session.refresh(sample_discovered_doc)
    assert sample_discovered_doc.status == "approved"

    # Rescan the document
    item = DiscoveredItem(
        title=sample_discovered_doc.title,
        source_page_url=sample_discovered_doc.source_page_url,
        download_url=sample_discovered_doc.download_url,
        category=sample_discovered_doc.category,
    )
    upsert_discovered_documents(db_session, "tnp-policy", [item])
    db_session.refresh(sample_discovered_doc)

    # Status must strictly remain 'approved'
    assert sample_discovered_doc.status == "approved"
    assert sample_discovered_doc.approved_by == admin_user.email


# ---------------------------------------------------------------------------
# 7. Stale Scan Recovery & Startup Handling (Issue 1)
# ---------------------------------------------------------------------------


def test_stale_scan_startup_recovery(db_session):
    """Verify startup recovery marks orphaned running scans failed while preserving completed ones."""
    from crawler.catalog import recover_stale_scans_on_startup

    # Create one running scan (simulating crash) and one completed scan
    crashed_scan = CrawlerScan(
        id=uuid.uuid4(),
        status="running",
        initiated_by="admin@pec.edu.in",
        started_at=datetime.now(timezone.utc),
    )
    completed_scan = CrawlerScan(
        id=uuid.uuid4(),
        status="completed",
        initiated_by="admin@pec.edu.in",
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )
    db_session.add_all([crashed_scan, completed_scan])
    db_session.commit()

    # Run startup recovery
    recovered_count = recover_stale_scans_on_startup(db_session)
    assert recovered_count >= 1

    db_session.refresh(crashed_scan)
    db_session.refresh(completed_scan)

    assert crashed_scan.status == "failed"
    assert "application restart" in crashed_scan.error_message
    assert crashed_scan.completed_at is not None

    # Completed scan must be untouched
    assert completed_scan.status == "completed"

    # After recovery, a new scan can start cleanly without conflict
    new_scan = start_scan_execution(db_session, initiated_by="admin@pec.edu.in")
    assert new_scan.status == "running"

    # Cleanup
    db_session.delete(crashed_scan)
    db_session.delete(completed_scan)
    db_session.delete(new_scan)
    db_session.commit()


def test_stale_scan_timeout_in_start_scan_execution(db_session):
    """Verify scans running longer than timeout threshold (30m) are recovered upon new scan attempt."""
    from datetime import timedelta
    old_time = datetime.now(timezone.utc) - timedelta(minutes=45)
    stale_scan = CrawlerScan(
        id=uuid.uuid4(),
        status="running",
        initiated_by="admin@pec.edu.in",
        started_at=old_time,
    )
    db_session.add(stale_scan)
    db_session.commit()

    # Attempting to start a scan should automatically timeout the stale scan and succeed
    new_scan = start_scan_execution(db_session, initiated_by="admin@pec.edu.in")
    assert new_scan is not None
    assert new_scan.status == "running"

    db_session.refresh(stale_scan)
    assert stale_scan.status == "failed"
    assert "timeout threshold" in stale_scan.error_message

    # Cleanup
    db_session.delete(stale_scan)
    db_session.delete(new_scan)
    db_session.commit()


# ---------------------------------------------------------------------------
# 8. Database Concurrency Lock via Partial Unique Index (Issue 3)
# ---------------------------------------------------------------------------


def test_database_level_concurrency_race_condition(db_session):
    """Simulate two simultaneous requests trying to start running scans and verify DB partial unique index enforces safety."""
    scan1 = start_scan_execution(db_session, initiated_by="admin1@pec.edu.in")
    assert scan1.status == "running"

    # A second request in a separate session/transaction attempting to start should raise RuntimeError
    session2 = SessionLocal()
    try:
        with pytest.raises(RuntimeError, match="already in progress"):
            start_scan_execution(session2, initiated_by="admin2@pec.edu.in")
    finally:
        session2.close()

    # Cleanup
    db_session.delete(scan1)
    db_session.commit()


# ---------------------------------------------------------------------------
# 9. Isolated Per-Source Failure Handling (Issue 4)
# ---------------------------------------------------------------------------


def test_isolated_source_failures_partial_success(db_session):
    """Verify that if one source fails, remaining sources continue and the scan completes with partial summary."""
    from api.routes.crawler import _execute_background_scan

    # Seed sources
    sources = seed_default_sources(db_session)
    source_ids = [s.source_id for s in sources[:2]]

    scan = start_scan_execution(db_session, initiated_by="admin@pec.edu.in")
    scan_id = scan.id

    # Mock engine so that source 1 fails with Exception, while source 2 succeeds
    mock_items = [
        DiscoveredItem(
            title="Valid Document from Source 2",
            source_page_url="https://pec.ac.in/valid",
            download_url="https://pec.ac.in/valid/doc.pdf",
            category="Academic",
        )
    ]

    def mock_scan_source(cfg):
        if cfg.source_id == source_ids[0]:
            raise ConnectionError("Simulated network timeout connecting to PEC server")
        return mock_items

    with patch("api.routes.crawler.PECCrawlerEngine") as MockEngineCls:
        mock_instance = MagicMock()
        mock_instance.scan_source.side_effect = mock_scan_source
        MockEngineCls.return_value = mock_instance

        # Execute scan
        _execute_background_scan(scan_id=scan_id, source_id=None)

    # Check scan outcome
    db_session.refresh(scan)
    assert scan.status == "completed"
    assert scan.error_message is not None
    assert "Partial scan success" in scan.error_message
    assert "Simulated network timeout" in scan.error_message

    # Verify document from source 2 was successfully persisted despite source 1 failure
    doc = db_session.query(DiscoveredDocument).filter_by(download_url="https://pec.ac.in/valid/doc.pdf").first()
    assert doc is not None
    assert doc.title == "Valid Document from Source 2"

    # Cleanup
    if doc:
        db_session.delete(doc)
    db_session.delete(scan)
    db_session.commit()


def test_isolated_source_failures_all_fail(db_session):
    """Verify that if all sources fail, the scan status is marked failed with full diagnostic error message."""
    from api.routes.crawler import _execute_background_scan

    scan = start_scan_execution(db_session, initiated_by="admin@pec.edu.in")
    scan_id = scan.id

    with patch("api.routes.crawler.PECCrawlerEngine") as MockEngineCls:
        mock_instance = MagicMock()
        mock_instance.scan_source.side_effect = RuntimeError("All PEC web endpoints down")
        MockEngineCls.return_value = mock_instance

        _execute_background_scan(scan_id=scan_id, source_id="tnp-policy")

    db_session.refresh(scan)
    assert scan.status == "failed"
    assert "failed" in scan.error_message.lower()
    assert "All PEC web endpoints down" in scan.error_message

    # Cleanup
    db_session.delete(scan)
    db_session.commit()


def test_isolated_source_failures_no_enabled_sources(db_session):
    """Verify that if no sources are enabled, the scan completes safely with an informative message."""
    from api.routes.crawler import _execute_background_scan

    # Disable all sources temporarily
    all_sources = get_all_sources(db_session)
    original_states = {s.source_id: s.enabled for s in all_sources}
    for s in all_sources:
        s.enabled = False
    db_session.commit()

    try:
        scan = start_scan_execution(db_session, initiated_by="admin@pec.edu.in")
        scan_id = scan.id

        _execute_background_scan(scan_id=scan_id, source_id=None)

        db_session.refresh(scan)
        assert scan.status == "completed"
        assert "No enabled crawler sources" in scan.error_message
        assert scan.total_discovered == 0
    finally:
        # Restore source states
        for s in all_sources:
            s.enabled = original_states[s.source_id]
        db_session.delete(scan)
        db_session.commit()
