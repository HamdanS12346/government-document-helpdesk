"""Application settings loaded from environment variables."""

from functools import cache
from typing import Optional

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the backend application."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    app_name: str = "govt-doc-helpdesk"
    chat_debug_prints: bool = Field(default=False, validation_alias="CHAT_DEBUG_PRINTS")

    langfuse_enabled: bool = Field(default=False, validation_alias="LANGFUSE_ENABLED")
    langfuse_public_key: Optional[str] = Field(
        default=None,
        validation_alias="LANGFUSE_PUBLIC_KEY",
    )
    langfuse_secret_key: Optional[str] = Field(
        default=None,
        validation_alias="LANGFUSE_SECRET_KEY",
    )
    langfuse_base_url: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("LANGFUSE_BASE_URL", "LANGFUSE_HOST"),
    )
    langfuse_capture_text: bool = Field(
        default=False,
        validation_alias="LANGFUSE_CAPTURE_TEXT",
    )


@cache
def get_settings() -> Settings:
    """Return cached application settings."""

    return Settings()


__all__ = ["Settings", "get_settings"]
