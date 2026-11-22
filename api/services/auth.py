"""Google OAuth token verification and server-side session management."""

import hashlib
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.config import get_api_settings
from database.models import Session as SessionModel, User

logger = logging.getLogger(__name__)


class AuthError(Exception):
    """Base exception for authentication failures."""

    def __init__(self, message: str, status_code: int = 401):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def hash_token(raw_token: str) -> str:
    """Compute SHA-256 hex digest of a raw opaque session token."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def verify_google_id_token(
    id_token_str: str,
    client_id: Optional[str] = None,
    request_adapter: Optional[Any] = None,
) -> dict[str, Any]:
    """Independently verify Google OpenID Connect ID token signature, claims, and audience.

    Parameters
    ----------
    id_token_str : str
        The raw JWT token received from Google Identity Services.
    client_id : Optional[str]
        Expected Google OAuth client ID audience. If omitted, uses backend configuration.
    request_adapter : Optional[Any]
        Google auth transport adapter (allows injecting mock in tests).

    Returns
    -------
    dict[str, Any]
        The verified token payload containing sub, email, email_verified, name, picture.

    Raises
    ------
    AuthError
        If verification fails or required claims are missing/unverified.
    """
    settings = get_api_settings()
    is_dev = settings.app_env.strip().lower() == "development"

    # 1. Mock token handling: strict fail-closed
    if id_token_str.startswith("dev_mock_"):
        if not is_dev:
            logger.warning("Mock authentication attempted outside development mode (app_env=%s)", settings.app_env)
            raise AuthError("Mock authentication is disabled in production.", status_code=401)

        if id_token_str == "dev_mock_admin":
            admin_email = settings.admin_emails_list[0] if settings.admin_emails_list else "admin@pec.edu.in"
            return {
                "iss": "https://accounts.google.com",
                "sub": "dev_mock_admin_sub_001",
                "email": admin_email,
                "email_verified": True,
                "name": "IRIS Administrator",
                "picture": None,
            }
        elif id_token_str == "dev_mock_pec_student":
            return {
                "iss": "https://accounts.google.com",
                "sub": "dev_mock_student_sub_002",
                "email": "student@pec.edu.in",
                "email_verified": True,
                "name": "PEC Student",
                "picture": None,
            }
        else:
            logger.warning("Unknown mock token supplied: %s", id_token_str)
            raise AuthError("Unsupported mock authentication token.", status_code=401)

    # 2. Real Google token verification: client_id / audience is mandatory in dev and prod
    expected_client_id = (client_id or settings.google_client_id or "").strip()
    if not expected_client_id:
        logger.error("Authentication rejected: GOOGLE_CLIENT_ID is not configured.")
        raise AuthError("Authentication service is temporarily unavailable due to configuration.", status_code=500)

    adapter = request_adapter or google_requests.Request()
    try:
        payload = id_token.verify_oauth2_token(
            id_token_str,
            adapter,
            audience=expected_client_id,
        )
    except Exception as exc:
        logger.warning("Google ID token verification failed: %s", exc)
        raise AuthError("Invalid or expired authentication token.", status_code=401) from exc

    # Validate issuer
    issuer = payload.get("iss")
    if issuer not in ("accounts.google.com", "https://accounts.google.com"):
        logger.warning("Token rejected: untrusted issuer '%s'", issuer)
        raise AuthError("Invalid authentication token issuer.", status_code=401)

    # Validate email verification
    if not payload.get("email_verified"):
        raise AuthError("Google account email is not verified.", status_code=403)

    if not payload.get("sub") or not payload.get("email"):
        raise AuthError("Authentication token is missing required identity claims.", status_code=400)

    return payload


def determine_user_eligibility(
    email: str,
    allowed_domains: list[str],
    admin_emails: list[str],
) -> tuple[bool, str]:
    """Determine whether a verified email is eligible to access IRIS, and assign role.

    Rules:
    - If email is in admin_emails: eligible, role="admin"
    - If email domain matches any allowed_domains: eligible, role="user"
    - Otherwise: ineligible, role="user"
    """
    norm_email = email.strip().lower()

    # 1. Administrator allowlist takes precedence (allows personal emails)
    if norm_email in admin_emails:
        return True, "admin"

    # 2. Check institutional domain match
    for domain in allowed_domains:
        clean_domain = domain.strip().lower()
        if norm_email.endswith(f"@{clean_domain}"):
            return True, "user"

    return False, "user"


def authenticate_or_register_user(
    token_payload: dict[str, Any],
    db: Session,
) -> User:
    """Find or create user record based on verified Google token payload.

    Enforces institutional eligibility and administrative role assignments.
    """
    settings = get_api_settings()
    google_sub = token_payload["sub"]
    raw_email = token_payload["email"]
    norm_email = raw_email.strip().lower()
    name = token_payload.get("name") or norm_email.split("@")[0]
    picture = token_payload.get("picture")

    # Check eligibility
    is_eligible, role = determine_user_eligibility(
        norm_email,
        settings.allowed_domains_list,
        settings.admin_emails_list,
    )

    if not is_eligible:
        logger.warning("Access denied for ineligible email: %s", norm_email)
        allowed_desc = ", ".join(settings.allowed_domains_list) or "PEC institutional domain"
        raise AuthError(
            f"Access restricted to authorized {allowed_desc} accounts and administrators.",
            status_code=403,
        )

    # Find existing user by Google sub first (stable identity anchor)
    user = db.scalar(select(User).where(User.google_sub == google_sub))

    if user:
        # Verified user matched by google_sub: handle email updates if changed in Google Workspace
        if user.email != norm_email:
            conflict_user = db.scalar(
                select(User).where(User.email == norm_email, User.id != user.id)
            )
            if conflict_user:
                logger.warning(
                    "Email collision: sub %s wants email %s, which is already held by user %s (sub %s)",
                    google_sub, norm_email, conflict_user.id, conflict_user.google_sub
                )
                raise AuthError(
                    "Email address is already linked to another user account.",
                    status_code=409,
                )
            logger.info("Updating verified email for sub %s: %s -> %s", google_sub, user.email, norm_email)
            user.email = norm_email
    else:
        # Check by email in case account was pre-seeded without sub
        existing_by_email = db.scalar(select(User).where(User.email == norm_email))
        if existing_by_email:
            if existing_by_email.google_sub and existing_by_email.google_sub != google_sub:
                logger.warning(
                    "Identity collision: email %s already bound to sub %s, rejected incoming sub %s",
                    norm_email, existing_by_email.google_sub, google_sub
                )
                raise AuthError(
                    "Email address is already linked to a different Google account.",
                    status_code=409,
                )
            user = existing_by_email
            user.google_sub = google_sub

    now = datetime.now(timezone.utc)

    if user:
        if not user.is_active:
            raise AuthError("Your account has been deactivated.", status_code=403)

        # Update mutable profile info and role
        user.name = name
        user.profile_picture_url = picture
        user.role = role  # Keep role synchronized with backend config
        user.last_login_at = now
        user.updated_at = now
    else:
        # Create new user
        user = User(
            google_sub=google_sub,
            email=norm_email,
            name=name,
            profile_picture_url=picture,
            role=role,
            is_active=True,
            created_at=now,
            updated_at=now,
            last_login_at=now,
        )
        db.add(user)

    db.commit()
    db.refresh(user)
    return user


def create_user_session(
    user_id: uuid.UUID,
    db: Session,
    expire_days: int = 7,
) -> tuple[str, SessionModel]:
    """Generate a cryptographic opaque session token and store its SHA-256 hash in DB."""
    raw_token = secrets.token_urlsafe(32)
    token_hashed = hash_token(raw_token)

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=expire_days)

    session = SessionModel(
        user_id=user_id,
        token_hash=token_hashed,
        expires_at=expires_at,
        created_at=now,
        revoked_at=None,
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    return raw_token, session


def validate_session_token(raw_token: str, db: Session) -> Optional[User]:
    """Look up active session by hashed token and return the authenticated User."""
    if not raw_token or not raw_token.strip():
        return None

    token_hashed = hash_token(raw_token.strip())
    now = datetime.now(timezone.utc)

    stmt = (
        select(SessionModel)
        .where(
            SessionModel.token_hash == token_hashed,
            SessionModel.revoked_at.is_(None),
            SessionModel.expires_at > now,
        )
    )
    session_record = db.scalar(stmt)

    if not session_record or not session_record.user:
        return None

    if not session_record.user.is_active:
        return None

    return session_record.user


def revoke_session_token(raw_token: str, db: Session) -> bool:
    """Revoke an active session token by setting its revoked_at timestamp."""
    if not raw_token:
        return False

    token_hashed = hash_token(raw_token.strip())
    session_record = db.scalar(
        select(SessionModel).where(SessionModel.token_hash == token_hashed)
    )

    if session_record and session_record.revoked_at is None:
        session_record.revoked_at = datetime.now(timezone.utc)
        db.commit()
        return True

    return False
