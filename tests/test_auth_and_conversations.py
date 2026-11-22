"""Comprehensive unit and integration tests for Authentication, Authorization, and Conversation History."""

import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api.config import APISettings, get_api_settings
from api.dependencies import get_current_user, get_database_session, require_admin
from api.main import create_application
from api.services.auth import (
    AuthError,
    authenticate_or_register_user,
    create_user_session,
    determine_user_eligibility,
    hash_token,
    revoke_session_token,
    validate_session_token,
    verify_google_id_token,
)
from database.connection import Base
from database.models import Conversation, Message, Session as SessionModel, User
from rag.models import Citation, RAGResponse


# ---------------------------------------------------------------------------
# Test SQLite In-Memory Database Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="function")
def test_db():
    """In-memory SQLite database for isolated authentication and conversation tests."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    # Note: Vector type is for postgres; SQLite mock uses tables without Vector columns
    Base.metadata.create_all(
        bind=engine,
        tables=[
            User.__table__,
            SessionModel.__table__,
            Conversation.__table__,
            Message.__table__,
        ],
    )

    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(
            bind=engine,
            tables=[
                Message.__table__,
                Conversation.__table__,
                SessionModel.__table__,
                User.__table__,
            ],
        )


@pytest.fixture
def test_app(test_db):
    """FastAPI app instance wired to the in-memory test database."""
    app = create_application()
    app.dependency_overrides[get_database_session] = lambda: test_db
    yield app
    app.dependency_overrides.clear()


@pytest.fixture
def client(test_app):
    """TestClient wired to the test application."""
    with TestClient(test_app) as c:
        yield c


# ---------------------------------------------------------------------------
# 1. Google ID Token Verification Unit Tests
# ---------------------------------------------------------------------------

def test_verify_google_id_token_success():
    """Verify Google token decoding with valid claims and audience."""
    mock_payload = {
        "iss": "https://accounts.google.com",
        "sub": "google_12345",
        "email": "student@pec.edu.in",
        "email_verified": True,
        "name": "PEC Student",
        "picture": "https://example.com/pic.jpg",
    }
    with patch("google.oauth2.id_token.verify_oauth2_token", return_value=mock_payload):
        claims = verify_google_id_token("fake_valid_jwt_token", client_id="test_client_id")
        assert claims["sub"] == "google_12345"
        assert claims["email"] == "student@pec.edu.in"
        assert claims["email_verified"] is True


def test_verify_google_id_token_invalid_signature():
    """Verify that an invalid signature raises AuthError with safe error message."""
    with patch(
        "google.oauth2.id_token.verify_oauth2_token",
        side_effect=ValueError("Token expired"),
    ):
        with pytest.raises(AuthError) as exc_info:
            verify_google_id_token("expired_token", client_id="test_client_id")
        assert exc_info.value.status_code == 401
        assert "Invalid or expired" in exc_info.value.message


def test_verify_google_id_token_invalid_issuer():
    """Verify that a forged token from an untrusted issuer is rejected."""
    mock_payload = {
        "iss": "https://evil-issuer.com",
        "sub": "google_12345",
        "email": "student@pec.edu.in",
        "email_verified": True,
    }
    with patch("google.oauth2.id_token.verify_oauth2_token", return_value=mock_payload):
        with pytest.raises(AuthError) as exc_info:
            verify_google_id_token("untrusted_issuer_token", client_id="test_client_id")
        assert exc_info.value.status_code == 401
        assert "Invalid authentication token issuer" in exc_info.value.message


def test_verify_google_id_token_unverified_email():
    """Verify that an unverified Google email is rejected."""
    mock_payload = {
        "iss": "accounts.google.com",
        "sub": "google_12345",
        "email": "unverified@pec.edu.in",
        "email_verified": False,
    }
    with patch("google.oauth2.id_token.verify_oauth2_token", return_value=mock_payload):
        with pytest.raises(AuthError) as exc_info:
            verify_google_id_token("unverified_email_token", client_id="test_client_id")
        assert exc_info.value.status_code == 403
        assert "email is not verified" in exc_info.value.message


def test_verify_google_id_token_missing_client_id_fails_closed():
    """Verify that missing client ID raises a 500 configuration error and does not verify without audience."""
    with patch.dict("os.environ", {"GOOGLE_CLIENT_ID": ""}):
        import api.config
        api.config._settings_instance = None
        with pytest.raises(AuthError) as exc_info:
            verify_google_id_token("some_token", client_id=None)
        assert exc_info.value.status_code == 500
        assert "configuration" in exc_info.value.message.lower()


def test_verify_google_id_token_mock_rejected_in_production():
    """Verify that mock tokens are rejected with 401 when APP_ENV != development."""
    with patch.dict("os.environ", {"APP_ENV": "production"}):
        import api.config
        api.config._settings_instance = None
        with pytest.raises(AuthError) as exc_info:
            verify_google_id_token("dev_mock_pec_student")
        assert exc_info.value.status_code == 401
        assert "disabled in production" in exc_info.value.message


def test_verify_google_id_token_unknown_mock_rejected():
    """Verify that unrecognized mock tokens are rejected."""
    with patch.dict("os.environ", {"APP_ENV": "development"}):
        import api.config
        api.config._settings_instance = None
        with pytest.raises(AuthError) as exc_info:
            verify_google_id_token("dev_mock_unsupported_hacker")
        assert exc_info.value.status_code == 401
        assert "Unsupported mock" in exc_info.value.message


# ---------------------------------------------------------------------------
# 2. Eligibility & Role Determination Unit Tests
# ---------------------------------------------------------------------------

def test_determine_eligibility_institutional_user():
    """Regular institutional email gets role='user'."""
    allowed = ["pec.edu.in"]
    admins = ["admin@example.com"]

    is_eligible, role = determine_user_eligibility("student@pec.edu.in", allowed, admins)
    assert is_eligible is True
    assert role == "user"

    # Case insensitivity test
    is_eligible_upper, role_upper = determine_user_eligibility("STUDENT@PEC.EDU.IN", allowed, admins)
    assert is_eligible_upper is True
    assert role_upper == "user"


def test_determine_eligibility_personal_admin():
    """Personal Google account in ADMIN_EMAILS gets role='admin' regardless of domain."""
    allowed = ["pec.edu.in"]
    admins = ["my.personal.account@gmail.com"]

    is_eligible, role = determine_user_eligibility(
        "my.personal.account@gmail.com", allowed, admins
    )
    assert is_eligible is True
    assert role == "admin"


def test_determine_eligibility_disallowed_external_user():
    """External email not in allowed domains or admin list is denied."""
    allowed = ["pec.edu.in"]
    admins = ["admin@pec.edu.in"]

    is_eligible, role = determine_user_eligibility("random.user@gmail.com", allowed, admins)
    assert is_eligible is False
    assert role == "user"


# ---------------------------------------------------------------------------
# 3. Session & User Management Unit Tests
# ---------------------------------------------------------------------------

def test_create_and_validate_session(test_db):
    """Verify session creation, token hashing, and lookup."""
    user = User(
        id=uuid.uuid4(),
        google_sub="sub_test_001",
        email="test@pec.edu.in",
        name="Test Student",
        role="user",
        is_active=True,
    )
    test_db.add(user)
    test_db.commit()

    raw_token, session_record = create_user_session(user.id, test_db, expire_days=1)
    assert raw_token is not None
    assert len(raw_token) > 20
    assert session_record.token_hash == hash_token(raw_token)
    # Raw token must NOT be stored in database
    assert session_record.token_hash != raw_token

    # Validate active token
    resolved_user = validate_session_token(raw_token, test_db)
    assert resolved_user is not None
    assert resolved_user.id == user.id

    # Revoke session
    revoked = revoke_session_token(raw_token, test_db)
    assert revoked is True

    # Revoked session must fail validation
    assert validate_session_token(raw_token, test_db) is None


def test_expired_session_fails_validation(test_db):
    """Verify expired sessions are rejected."""
    user = User(
        id=uuid.uuid4(),
        google_sub="sub_test_002",
        email="test2@pec.edu.in",
        name="Test Student 2",
        role="user",
        is_active=True,
    )
    test_db.add(user)
    test_db.commit()

    raw_token, session_record = create_user_session(user.id, test_db, expire_days=1)
    # Manually expire session
    session_record.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    test_db.commit()

    assert validate_session_token(raw_token, test_db) is None


# ---------------------------------------------------------------------------
# 4. Auth API Endpoints Integration Tests
# ---------------------------------------------------------------------------

def test_auth_google_success_institutional_user(client, test_db):
    """POST /auth/google creates user, session, and sets HttpOnly cookie."""
    mock_payload = {
        "iss": "https://accounts.google.com",
        "sub": "sub_pec_100",
        "email": "student100@pec.edu.in",
        "email_verified": True,
        "name": "PEC Student 100",
        "picture": "https://pic.pec.edu.in/100.png",
    }

    with patch("api.routes.auth.verify_google_id_token", return_value=mock_payload):
        resp = client.post("/auth/google", json={"id_token": "valid_token_xyz"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == "student100@pec.edu.in"
        assert data["name"] == "PEC Student 100"
        assert data["role"] == "user"
        assert "iris_session" in resp.cookies


def test_auth_google_success_admin_user(client, test_db):
    """POST /auth/google assigns admin role to personal email in ADMIN_EMAILS."""
    mock_payload = {
        "iss": "https://accounts.google.com",
        "sub": "sub_admin_999",
        "email": "personal.admin@gmail.com",
        "email_verified": True,
        "name": "IRIS Administrator",
        "picture": "https://pic.google.com/admin.png",
    }

    with patch("api.routes.auth.verify_google_id_token", return_value=mock_payload), \
         patch.dict("os.environ", {"ADMIN_EMAILS": "personal.admin@gmail.com"}):
        # Clear cached settings so ADMIN_EMAILS is re-read
        import api.config
        api.config._settings_instance = None

        resp = client.post("/auth/google", json={"id_token": "valid_admin_token"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == "personal.admin@gmail.com"
        assert data["role"] == "admin"
        assert "iris_session" in resp.cookies


def test_auth_google_disallowed_domain_rejected(client, test_db):
    """POST /auth/google returns 403 for unauthorized non-institutional email."""
    mock_payload = {
        "iss": "https://accounts.google.com",
        "sub": "sub_unauth_001",
        "email": "intruder@outsider.com",
        "email_verified": True,
        "name": "Outside User",
    }

    with patch("api.routes.auth.verify_google_id_token", return_value=mock_payload):
        resp = client.post("/auth/google", json={"id_token": "valid_token_outsider"})
        assert resp.status_code == 403
        assert "Access restricted" in resp.json()["detail"]
        assert "iris_session" not in resp.cookies


def test_auth_me_authenticated_and_unauthenticated(client, test_db):
    """GET /auth/me returns user profile with cookie, 401 without cookie."""
    # Unauthenticated
    resp_unauth = client.get("/auth/me")
    assert resp_unauth.status_code == 401

    # Authenticate user
    user = User(
        id=uuid.uuid4(),
        google_sub="sub_me_test",
        email="me@pec.edu.in",
        name="Me Student",
        role="user",
        is_active=True,
    )
    test_db.add(user)
    test_db.commit()

    raw_token, _ = create_user_session(user.id, test_db)
    client.cookies.set("iris_session", raw_token)

    resp_auth = client.get("/auth/me")
    assert resp_auth.status_code == 200
    assert resp_auth.json()["email"] == "me@pec.edu.in"


def test_auth_logout_clears_cookie_and_revokes_session(client, test_db):
    """POST /auth/logout revokes session in DB and deletes cookie."""
    user = User(
        id=uuid.uuid4(),
        google_sub="sub_logout_test",
        email="logout@pec.edu.in",
        name="Logout Student",
        role="user",
        is_active=True,
    )
    test_db.add(user)
    test_db.commit()

    raw_token, session_rec = create_user_session(user.id, test_db)
    client.cookies.set("iris_session", raw_token)

    resp = client.post("/auth/logout")
    assert resp.status_code == 200
    assert resp.json()["status"] == "logged_out"

    # Session in DB must now be revoked
    test_db.refresh(session_rec)
    assert session_rec.revoked_at is not None

    # Next call to /auth/me must fail with 401
    assert client.get("/auth/me").status_code == 401


# ---------------------------------------------------------------------------
# 5. Conversation History CRUD & Ownership Isolation Tests
# ---------------------------------------------------------------------------

def test_conversations_crud_and_isolation(client, test_db):
    """Test full CRUD operations on conversations and verify data isolation between users."""
    # User A
    user_a = User(
        id=uuid.uuid4(),
        google_sub="sub_a",
        email="user.a@pec.edu.in",
        name="User A",
        role="user",
        is_active=True,
    )
    # User B
    user_b = User(
        id=uuid.uuid4(),
        google_sub="sub_b",
        email="user.b@pec.edu.in",
        name="User B",
        role="user",
        is_active=True,
    )
    test_db.add_all([user_a, user_b])
    test_db.commit()

    # Log in as User A
    token_a, _ = create_user_session(user_a.id, test_db)
    client.cookies.set("iris_session", token_a)

    # 1. Create conversation for User A
    resp_create = client.post("/conversations", json={"title": "Cloud Computing Syllabus"})
    assert resp_create.status_code == 201
    conv_a_id = resp_create.json()["id"]
    assert resp_create.json()["title"] == "Cloud Computing Syllabus"

    # 2. List conversations for User A
    resp_list = client.get("/conversations")
    assert resp_list.status_code == 200
    assert resp_list.json()["total"] == 1
    assert resp_list.json()["items"][0]["id"] == conv_a_id

    # 3. Retrieve conversation for User A
    resp_get = client.get(f"/conversations/{conv_a_id}")
    assert resp_get.status_code == 200
    assert resp_get.json()["id"] == conv_a_id

    # 4. Rename conversation for User A
    resp_rename = client.patch(
        f"/conversations/{conv_a_id}",
        json={"title": "Cloud Computing Objectives & Units"},
    )
    assert resp_rename.status_code == 200
    assert resp_rename.json()["title"] == "Cloud Computing Objectives & Units"

    # 5. Switch to User B and verify strict ownership isolation
    token_b, _ = create_user_session(user_b.id, test_db)
    client.cookies.set("iris_session", token_b)

    # User B lists conversations -> empty!
    resp_b_list = client.get("/conversations")
    assert resp_b_list.status_code == 200
    assert resp_b_list.json()["total"] == 0

    # User B tries to read User A's conversation by UUID -> 404!
    resp_b_get = client.get(f"/conversations/{conv_a_id}")
    assert resp_b_get.status_code == 404

    # User B tries to rename User A's conversation -> 404!
    resp_b_patch = client.patch(
        f"/conversations/{conv_a_id}",
        json={"title": "Malicious Rename"},
    )
    assert resp_b_patch.status_code == 404

    # User B tries to delete User A's conversation -> 404!
    resp_b_del = client.delete(f"/conversations/{conv_a_id}")
    assert resp_b_del.status_code == 404

    # 6. Switch back to User A and delete
    client.cookies.set("iris_session", token_a)
    resp_del = client.delete(f"/conversations/{conv_a_id}")
    assert resp_del.status_code == 200
    assert resp_del.json()["status"] == "deleted"

    # Verify deleted
    assert client.get(f"/conversations/{conv_a_id}").status_code == 404


# ---------------------------------------------------------------------------
# 6. Chat Endpoint with Authentication & Conversation Persistence Tests
# ---------------------------------------------------------------------------

def test_chat_unauthenticated_rejected(client):
    """POST /chat rejects unauthenticated requests with 401."""
    client.cookies.clear()
    resp = client.post("/chat", json={"query": "What are course objectives?"})
    assert resp.status_code == 401
    assert "Authentication required" in resp.json()["detail"]


def test_chat_creates_conversation_and_persists_messages(client, test_db):
    """POST /chat without conversation_id auto-creates conversation and persists Q&A."""
    user = User(
        id=uuid.uuid4(),
        google_sub="sub_chat_persister",
        email="persister@pec.edu.in",
        name="Chat Persister",
        role="user",
        is_active=True,
    )
    test_db.add(user)
    test_db.commit()

    raw_token, _ = create_user_session(user.id, test_db)
    client.cookies.set("iris_session", raw_token)

    mock_rag = RAGResponse(
        query="What are the course objectives of Cloud Computing?",
        status="answered",
        answer="The objectives include distributed computing principles.",
        citations=[
            Citation(
                document="CSE_syllabus_24.pdf",
                pages=[117],
                chunk_id=uuid.uuid4(),
                section_title="Unit 7",
                page_spans=[],
                claim="Distributed principles",
                is_valid=True,
                claim_supported=True,
            )
        ],
        clarification_question=None,
        limitations=None,
        handoff_recommendation=None,
        retrieved_results=[],
    )

    with patch("api.routes.chat.answer_question", return_value=mock_rag):
        resp = client.post(
            "/chat",
            json={"query": "What are the course objectives of Cloud Computing?", "top_k": 5},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "answered"
        assert data["conversation_id"] is not None
        assert data["message_id"] is not None

        conv_id = data["conversation_id"]

        # Fetch conversation history through GET /conversations/{id}
        resp_conv = client.get(f"/conversations/{conv_id}")
        assert resp_conv.status_code == 200
        conv_data = resp_conv.json()
        assert len(conv_data["messages"]) == 2

        # Message 1: User question
        assert conv_data["messages"][0]["role"] == "user"
        assert conv_data["messages"][0]["content"] == "What are the course objectives of Cloud Computing?"

        # Message 2: Assistant response
        assert conv_data["messages"][1]["role"] == "assistant"
        assert conv_data["messages"][1]["status"] == "answered"
        assert conv_data["messages"][1]["citations"][0]["document"] == "CSE_syllabus_24.pdf"


def test_chat_appends_to_existing_conversation(client, test_db):
    """POST /chat with conversation_id appends to that existing thread."""
    user = User(
        id=uuid.uuid4(),
        google_sub="sub_threader",
        email="threader@pec.edu.in",
        name="Threader User",
        role="user",
        is_active=True,
    )
    test_db.add(user)
    test_db.commit()

    raw_token, _ = create_user_session(user.id, test_db)
    client.cookies.set("iris_session", raw_token)

    # Pre-create conversation
    conv = Conversation(user_id=user.id, title="Pre-created Thread")
    test_db.add(conv)
    test_db.commit()

    mock_rag = RAGResponse(
        query="Follow up question",
        status="answered",
        answer="Follow up answer.",
        citations=[],
        clarification_question=None,
        limitations=None,
        handoff_recommendation=None,
        retrieved_results=[],
    )

    with patch("api.routes.chat.answer_question", return_value=mock_rag):
        resp = client.post(
            "/chat",
            json={
                "query": "Follow up question",
                "conversation_id": str(conv.id),
                "top_k": 3,
            },
        )
        assert resp.status_code == 200
        assert resp.json()["conversation_id"] == str(conv.id)

        # Confirm thread has 2 messages
        resp_conv = client.get(f"/conversations/{conv.id}")
        assert resp_conv.status_code == 200
        assert len(resp_conv.json()["messages"]) == 2


# ---------------------------------------------------------------------------
# 7. Security Regression Tests (M11 Audit Fixes)
# ---------------------------------------------------------------------------

def test_authenticate_updates_verified_email_for_existing_sub(test_db):
    """When Google returns an updated verified email for an existing sub, update User.email safely."""
    now = datetime.now(timezone.utc)
    user = User(
        id=uuid.uuid4(),
        google_sub="sub_evolving_email",
        email="old.name@pec.edu.in",
        name="Student Evolving",
        role="user",
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    test_db.add(user)
    test_db.commit()

    token_payload = {
        "sub": "sub_evolving_email",
        "email": "new.name@pec.edu.in",
        "name": "Student Evolving Updated",
        "picture": None,
    }
    updated_user = authenticate_or_register_user(token_payload, test_db)
    assert updated_user.id == user.id
    assert updated_user.email == "new.name@pec.edu.in"
    assert updated_user.name == "Student Evolving Updated"


def test_authenticate_email_conflict_raises_409(test_db):
    """If incoming token sub attempts to use an email already held by a different user, reject with 409."""
    now = datetime.now(timezone.utc)
    user_a = User(
        id=uuid.uuid4(),
        google_sub="sub_alice",
        email="alice@pec.edu.in",
        name="Alice",
        role="user",
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    user_b = User(
        id=uuid.uuid4(),
        google_sub="sub_bob",
        email="bob@pec.edu.in",
        name="Bob",
        role="user",
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    test_db.add_all([user_a, user_b])
    test_db.commit()

    # Bob's sub attempts to claim Alice's email
    colliding_payload = {
        "sub": "sub_bob",
        "email": "alice@pec.edu.in",
        "name": "Bob Impersonator",
    }
    with pytest.raises(AuthError) as exc_info:
        authenticate_or_register_user(colliding_payload, test_db)
    assert exc_info.value.status_code == 409
    assert "already linked" in exc_info.value.message


def test_chat_cross_user_isolation(client, test_db):
    """User B cannot post a query to User A's conversation via POST /chat (must return 404)."""
    user_a = User(
        id=uuid.uuid4(),
        google_sub="sub_chat_a",
        email="user_a@pec.edu.in",
        name="User A",
        role="user",
        is_active=True,
    )
    user_b = User(
        id=uuid.uuid4(),
        google_sub="sub_chat_b",
        email="user_b@pec.edu.in",
        name="User B",
        role="user",
        is_active=True,
    )
    test_db.add_all([user_a, user_b])
    test_db.commit()

    # User A creates a conversation
    conv_a = Conversation(user_id=user_a.id, title="User A Confidential Thread")
    test_db.add(conv_a)
    test_db.commit()

    # User B logs in
    token_b, _ = create_user_session(user_b.id, test_db)
    client.cookies.set("iris_session", token_b)

    # User B tries to send a message to User A's thread
    resp = client.post(
        "/chat",
        json={
            "query": "Malicious attempt to write to User A's conversation",
            "conversation_id": str(conv_a.id),
        },
    )
    assert resp.status_code == 404
    assert "thread not found" in resp.json()["detail"].lower()


def test_active_session_admin_revocation(client, test_db):
    """Personal admin removed from ADMIN_EMAILS has active session rejected with 403 on subsequent requests."""
    admin_user = User(
        id=uuid.uuid4(),
        google_sub="sub_personal_admin",
        email="temp_admin@gmail.com",
        name="Temporary Admin",
        role="admin",
        is_active=True,
    )
    test_db.add(admin_user)
    test_db.commit()

    token, _ = create_user_session(admin_user.id, test_db)
    client.cookies.set("iris_session", token)

    # Initially ADMIN_EMAILS contains temp_admin@gmail.com
    with patch.dict("os.environ", {"ADMIN_EMAILS": "temp_admin@gmail.com"}):
        import api.config
        api.config._settings_instance = None

        resp = client.get("/auth/me")
        assert resp.status_code == 200
        assert resp.json()["role"] == "admin"

    # Now simulate removing temp_admin@gmail.com from ADMIN_EMAILS
    try:
        with patch.dict("os.environ", {"ADMIN_EMAILS": ""}):
            api.config._settings_instance = None

            # Personal Gmail is no longer eligible under ALLOWED_EMAIL_DOMAINS (pec.edu.in)
            resp_after = client.get("/auth/me")
            assert resp_after.status_code == 403
            assert "no longer authorized" in resp_after.json()["detail"].lower()
    finally:
        api.config._settings_instance = None


def test_active_session_institutional_role_downgrade(client, test_db):
    """Institutional admin removed from ADMIN_EMAILS has their role downgraded to 'user' immediately."""
    inst_admin = User(
        id=uuid.uuid4(),
        google_sub="sub_inst_admin",
        email="prof.admin@pec.edu.in",
        name="Prof Admin",
        role="admin",
        is_active=True,
    )
    test_db.add(inst_admin)
    test_db.commit()

    token, _ = create_user_session(inst_admin.id, test_db)
    client.cookies.set("iris_session", token)

    # Simulate removing from ADMIN_EMAILS
    try:
        with patch.dict("os.environ", {"ADMIN_EMAILS": ""}):
            import api.config
            api.config._settings_instance = None

            # Still eligible as institutional user, but downgraded from admin to user
            resp = client.get("/auth/me")
            assert resp.status_code == 200
            assert resp.json()["role"] == "user"

            # Verify DB row was also updated
            test_db.refresh(inst_admin)
            assert inst_admin.role == "user"
    finally:
        api.config._settings_instance = None


def test_csrf_origin_check_blocks_malicious_origin(client, test_db):
    """State-changing requests with a cookie from an untrusted Origin are rejected with 403."""
    user = User(
        id=uuid.uuid4(),
        google_sub="sub_csrf_test",
        email="csrf@pec.edu.in",
        name="CSRF Student",
        role="user",
        is_active=True,
    )
    test_db.add(user)
    test_db.commit()

    token, _ = create_user_session(user.id, test_db)
    client.cookies.set("iris_session", token)

    resp = client.post(
        "/conversations",
        json={"title": "Attack Conversation"},
        headers={"Origin": "http://evil-attacker-site.com"},
    )
    assert resp.status_code == 403
    assert "Cross-origin request forbidden" in resp.json()["detail"]


def test_csrf_origin_check_allows_configured_origin(client, test_db):
    """State-changing requests from a configured Origin (e.g. http://localhost:5173) succeed."""
    user = User(
        id=uuid.uuid4(),
        google_sub="sub_csrf_allowed",
        email="csrf.good@pec.edu.in",
        name="Good Student",
        role="user",
        is_active=True,
    )
    test_db.add(user)
    test_db.commit()

    token, _ = create_user_session(user.id, test_db)
    client.cookies.set("iris_session", token)

    resp = client.post(
        "/conversations",
        json={"title": "Legitimate Conversation"},
        headers={"Origin": "http://localhost:5173"},
    )
    assert resp.status_code == 201
    assert resp.json()["title"] == "Legitimate Conversation"
