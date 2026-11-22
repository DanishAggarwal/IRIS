"""FastAPI dependencies for database sessions, settings, and authentication."""

import logging
from typing import Generator, Optional
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from api.config import APISettings, get_api_settings
from api.services.auth import (
    determine_user_eligibility,
    validate_session_token,
)
from database.connection import SessionLocal
from database.models import User

logger = logging.getLogger(__name__)


def get_database_session() -> Generator[Session, None, None]:
    """Dependency that yields a database session and ensures it is safely closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_settings() -> APISettings:
    """Dependency that returns the application API settings."""
    return get_api_settings()


def validate_csrf_origin(request: Request, settings: APISettings) -> None:
    """Validate Origin header on state-changing requests when authenticated via cookie."""
    if request.method in ("POST", "PATCH", "DELETE", "PUT"):
        origin = request.headers.get("origin")
        if origin:
            clean_origin = origin.rstrip("/")
            allowed = [o.rstrip("/") for o in settings.allowed_origins]
            if clean_origin not in allowed:
                logger.warning("CSRF check failed: Origin %s not in allowed origins %s", origin, allowed)
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Cross-origin request forbidden.",
                )


def get_session_token_from_request(
    request: Request,
    settings: APISettings,
) -> Optional[str]:
    """Extract opaque session token from HttpOnly cookie or Authorization Bearer header."""
    # 1. Primary: HttpOnly Cookie
    cookie_token = request.cookies.get(settings.session_cookie_name)
    if cookie_token and cookie_token.strip():
        return cookie_token.strip()

    # 2. Secondary: Authorization: Bearer <token>
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        bearer_token = auth_header[7:].strip()
        if bearer_token:
            return bearer_token

    return None


def get_current_user(
    request: Request,
    db: Session = Depends(get_database_session),
    settings: APISettings = Depends(get_settings),
) -> User:
    """FastAPI dependency resolving the currently authenticated User.

    Extracts session token from cookie/header, validates it against active,
    unrevoked sessions in the database, enforces dynamic policy eligibility,
    and synchronizes administrative roles against live configuration.
    """
    token = get_session_token_from_request(request, settings)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please sign in with your Google account.",
        )

    # If request is authenticated via cookie on a state-changing method, enforce origin check
    if request.cookies.get(settings.session_cookie_name):
        validate_csrf_origin(request, settings)

    user = validate_session_token(token, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session is invalid, expired, or revoked. Please sign in again.",
        )

    # Dynamic eligibility and role synchronization
    is_eligible, expected_role = determine_user_eligibility(
        user.email,
        settings.allowed_domains_list,
        settings.admin_emails_list,
    )

    if not is_eligible:
        logger.warning("Active session rejected: user %s is no longer eligible under current policy.", user.email)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access restricted: Account is no longer authorized under institutional policy.",
        )

    if user.role != expected_role:
        logger.info("Synchronizing role for user %s: %s -> %s", user.email, user.role, expected_role)
        user.role = expected_role
        db.commit()
        db.refresh(user)

    return user


def require_admin(
    current_user: User = Depends(get_current_user),
    settings: APISettings = Depends(get_settings),
) -> User:
    """FastAPI dependency ensuring current user possesses administrator privileges based on live configuration."""
    email_norm = current_user.email.strip().lower()
    if email_norm not in settings.admin_emails_list:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden: Administrator privileges required.",
        )
    return current_user
