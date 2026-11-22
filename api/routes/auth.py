"""Authentication and user session management routes."""

import logging
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from api.config import APISettings, get_api_settings
from api.dependencies import (
    get_current_user,
    get_database_session,
    get_session_token_from_request,
    get_settings,
    validate_csrf_origin,
)
from api.schemas import (
    ErrorResponse,
    GoogleAuthRequest,
    LogoutResponse,
    UserResponse,
)
from api.services.auth import (
    AuthError,
    authenticate_or_register_user,
    create_user_session,
    revoke_session_token,
    verify_google_id_token,
)
from database.models import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication & Sessions"])


@router.post(
    "/google",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"model": UserResponse, "description": "Successfully authenticated with Google."},
        400: {"model": ErrorResponse, "description": "Missing required claims in token."},
        401: {"model": ErrorResponse, "description": "Invalid, expired or forged token."},
        403: {"model": ErrorResponse, "description": "Account not authorized (domain or deactivated)."},
    },
    summary="Sign in with Google ID token",
    description=(
        "Verifies a Google OpenID Connect ID token independently on the backend. "
        "Validates signature, issuer, audience, and email verification. "
        "Enforces institutional domain eligibility and administrator allowlist, "
        "creates or updates the user profile, and establishes an HttpOnly session cookie."
    ),
)
def google_auth_endpoint(
    payload: GoogleAuthRequest,
    response: Response,
    request: Request,
    db: Session = Depends(get_database_session),
    settings: APISettings = Depends(get_settings),
) -> UserResponse:
    """Verify Google token, authenticate user, and issue session cookie."""
    validate_csrf_origin(request, settings)
    try:
        token_claims = verify_google_id_token(payload.id_token)
        user = authenticate_or_register_user(token_claims, db)
        raw_token, session_record = create_user_session(
            user.id, db, expire_days=settings.session_expire_days
        )
    except AuthError as auth_err:
        raise HTTPException(
            status_code=auth_err.status_code,
            detail=auth_err.message,
        ) from auth_err
    except Exception as exc:
        logger.error("Unexpected error during Google authentication: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while establishing your session.",
        ) from exc

    # Set HttpOnly session cookie
    max_age_seconds = settings.session_expire_days * 86400
    response.set_cookie(
        key=settings.session_cookie_name,
        value=raw_token,
        max_age=max_age_seconds,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path="/",
    )

    return UserResponse(
        id=user.id,
        email=user.email,
        name=user.name,
        profile_picture_url=user.profile_picture_url,
        role=user.role,
    )


@router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"model": UserResponse, "description": "Current user profile."},
        401: {"model": ErrorResponse, "description": "Unauthenticated or session expired."},
    },
    summary="Get current user profile",
    description="Returns profile information and role for the currently authenticated user.",
)
def get_current_user_endpoint(
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    """Return profile for the currently authenticated user."""
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        name=current_user.name,
        profile_picture_url=current_user.profile_picture_url,
        role=current_user.role,
    )


@router.post(
    "/logout",
    response_model=LogoutResponse,
    status_code=status.HTTP_200_OK,
    summary="Log out and revoke session",
    description="Revokes the current server session in the database and clears the session cookie.",
)
def logout_endpoint(
    request: Request,
    response: Response,
    db: Session = Depends(get_database_session),
    settings: APISettings = Depends(get_settings),
) -> LogoutResponse:
    """Revoke session token and clear authentication cookie."""
    validate_csrf_origin(request, settings)
    token = get_session_token_from_request(request, settings)
    if token:
        revoke_session_token(token, db)

    # Delete session cookie
    response.delete_cookie(
        key=settings.session_cookie_name,
        path="/",
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
    )

    return LogoutResponse(status="logged_out")
