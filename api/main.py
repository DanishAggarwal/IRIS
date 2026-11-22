"""FastAPI application entrypoint for IRIS Institutional Document RAG."""

from contextlib import asynccontextmanager
import logging
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.config import get_api_settings
from api.exceptions import setup_exception_handlers
from api.routes import auth, chat, conversations, crawler, health

# Configure application logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("iris.api")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager handling startup and shutdown events."""
    settings = get_api_settings()
    logger.info("Initializing IRIS API service...")
    logger.info(f"Environment: {settings.app_env}")
    logger.info(f"Allowed CORS Origins: {settings.allowed_origins}")

    # Recover stale/interrupted scans and acquisitions left from a previous process
    try:
        from database.connection import SessionLocal
        from crawler.acquisition import recover_stale_ingestions_on_startup
        from crawler.catalog import recover_stale_scans_on_startup

        with SessionLocal() as db:
            recovered_scans = recover_stale_scans_on_startup(db)
            if recovered_scans > 0:
                logger.warning("Recovered %d interrupted crawler scans on startup.", recovered_scans)

            recovered_ingestions = recover_stale_ingestions_on_startup(db)
            if recovered_ingestions > 0:
                logger.warning("Recovered %d interrupted document acquisitions on startup.", recovered_ingestions)
    except Exception as exc:
        logger.error("Failed to run crawler startup recovery: %s", exc)

    yield
    logger.info("Shutting down IRIS API service.")


def create_application() -> FastAPI:
    """Factory creating and configuring the FastAPI application instance."""
    settings = get_api_settings()

    app = FastAPI(
        title="IRIS Institutional Document RAG API",
        description=(
            "HTTP REST API for IRIS — a local-first question-answering assistant for Punjab Engineering College (PEC). "
            "Answers student questions grounded exclusively in authorized institutional documents (syllabi, course handouts) "
            "with precise page-level citations, ambiguity clarification, and safe institutional handoff recommendations."
        ),
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # Configure CORS Middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "Accept"],
    )

    # Configure centralized error handlers
    setup_exception_handlers(app)

    # Register route modules
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(conversations.router)
    app.include_router(chat.router)
    app.include_router(crawler.router)

    return app


app = create_application()
