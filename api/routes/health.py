"""Health and readiness monitoring endpoints."""

import os
from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.dependencies import get_database_session
from api.schemas import ErrorResponse, HealthResponse, ReadinessResponse

router = APIRouter(tags=["Health & Monitoring"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Liveness probe",
    description="Returns HTTP 200 to confirm that the FastAPI application process is running.",
)
def get_health() -> HealthResponse:
    """Liveness probe confirming application process is running."""
    return HealthResponse(status="ok", service="IRIS API")


@router.get(
    "/health/ready",
    response_model=ReadinessResponse,
    responses={
        200: {"model": ReadinessResponse, "description": "All dependencies are ready to serve requests."},
        503: {"model": ReadinessResponse, "description": "One or more critical dependencies are unavailable."},
    },
    summary="Readiness probe",
    description=(
        "Verifies that critical dependencies (PostgreSQL database connectivity and "
        "Gemini API configuration) are ready to serve traffic without making external quota-burning API calls."
    ),
)
def get_readiness(
    response: Response,
    db: Session = Depends(get_database_session),
) -> ReadinessResponse:
    """Readiness probe checking database connectivity and required configuration."""
    db_ok = False
    db_status = "unavailable"

    # 1. Test database connectivity with a lightweight ping
    try:
        db.execute(text("SELECT 1;"))
        db_ok = True
        db_status = "connected"
    except Exception:
        db_ok = False
        db_status = "unavailable"

    # 2. Verify Gemini API key configuration
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    config_ok = bool(api_key)
    config_status = "ready" if config_ok else "missing_api_key"

    # Determine readiness outcome
    if db_ok and config_ok:
        return ReadinessResponse(
            status="ready",
            service="IRIS API",
            database=db_status,
            configuration=config_status,
            detail=None,
        )

    # If any critical dependency is failing, return 503
    response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    failures = []
    if not db_ok:
        failures.append("Database is unreachable.")
    if not config_ok:
        failures.append("GEMINI_API_KEY is not configured in environment.")

    return ReadinessResponse(
        status="unavailable",
        service="IRIS API",
        database=db_status,
        configuration=config_status,
        detail="; ".join(failures),
    )
