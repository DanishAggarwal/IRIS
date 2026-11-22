"""API configuration settings loaded from environment variables."""

import os
from typing import Optional
from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()


class APISettings(BaseSettings):
    """Configuration settings for the IRIS FastAPI backend."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    api_host: str = Field(default="127.0.0.1", description="Host address to bind the API server")
    api_port: int = Field(default=8000, description="Port number to bind the API server")
    app_env: str = Field(default="production", description="Application environment (development/production)")
    cors_origins: str = Field(
        default="http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173",
        description="Comma-separated list of allowed CORS origins",
    )
    max_query_length: int = Field(default=1000, description="Maximum allowed character length for user questions")
    gemini_api_key: Optional[str] = Field(default=None, alias="GEMINI_API_KEY")
    gemini_generation_model_primary: str = Field(
        default="gemini-3.5-flash-lite",
        alias="GEMINI_GENERATION_MODEL_PRIMARY",
        description="Primary model for RAG answer generation",
    )
    gemini_generation_model_fallback: str = Field(
        default="gemini-3.1-flash-lite",
        alias="GEMINI_GENERATION_MODEL_FALLBACK",
        description="Fallback model for RAG answer generation when primary hits rate limits or quota",
    )

    # Authentication & User Management
    google_client_id: Optional[str] = Field(default=None, alias="GOOGLE_CLIENT_ID")
    allowed_email_domains: str = Field(
        default="pec.edu.in",
        description="Comma-separated allowed institutional email domains",
    )
    admin_emails: str = Field(
        default="",
        description="Comma-separated allowlist of personal administrator emails",
    )
    session_cookie_name: str = Field(
        default="iris_session",
        description="Name of the HTTP-only session cookie",
    )
    session_expire_days: int = Field(
        default=7,
        description="Session validity duration in days",
    )
    cookie_secure: bool = Field(
        default=False,
        description="Whether session cookie requires HTTPS (set to True in production)",
    )
    cookie_samesite: str = Field(
        default="lax",
        description="SameSite cookie policy ('lax', 'strict', or 'none')",
    )

    @property
    def allowed_domains_list(self) -> list[str]:
        """Parse comma-separated allowed_email_domains into a clean lowercase list."""
        if not self.allowed_email_domains:
            return []
        return [
            domain.strip().lower()
            for domain in self.allowed_email_domains.split(",")
            if domain.strip()
        ]

    @property
    def admin_emails_list(self) -> list[str]:
        """Parse comma-separated admin_emails into a clean lowercase list."""
        if not self.admin_emails:
            return []
        return [
            email.strip().lower()
            for email in self.admin_emails.split(",")
            if email.strip()
        ]

    @property
    def allowed_origins(self) -> list[str]:
        """Parse comma-separated cors_origins string into a clean list of origins."""
        if not self.cors_origins:
            return []
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


_settings_instance: Optional[APISettings] = None


def get_api_settings() -> APISettings:
    """Return cached or new APISettings instance."""
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = APISettings()
    return _settings_instance
