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
    app_env: str = Field(default="development", description="Application environment (development/production)")
    cors_origins: str = Field(
        default="http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173",
        description="Comma-separated list of allowed CORS origins",
    )
    max_query_length: int = Field(default=1000, description="Maximum allowed character length for user questions")
    gemini_api_key: Optional[str] = Field(default=None, alias="GEMINI_API_KEY")

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
