"""FastAPI dependencies for database sessions and application settings."""

from typing import Generator
from sqlalchemy.orm import Session

from api.config import APISettings, get_api_settings
from database.connection import SessionLocal


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
