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

    spreadsheet_supported_extension: str = Field(
        default=".xlsx",
        validation_alias="SPREADSHEET_SUPPORTED_EXTENSION",
    )
    spreadsheet_parser_package: str = Field(
        default="openpyxl",
        validation_alias="SPREADSHEET_PARSER_PACKAGE",
    )
    spreadsheet_max_visible_sheets: int = Field(
        default=5,
        ge=1,
        validation_alias="SPREADSHEET_MAX_VISIBLE_SHEETS",
    )
    spreadsheet_max_rows_per_sheet: int = Field(
        default=50,
        ge=1,
        validation_alias="SPREADSHEET_MAX_ROWS_PER_SHEET",
    )
    spreadsheet_max_columns_per_sheet: int = Field(
        default=50,
        ge=1,
        validation_alias="SPREADSHEET_MAX_COLUMNS_PER_SHEET",
    )
    spreadsheet_max_text_cell_characters: int = Field(
        default=5_000,
        ge=1,
        validation_alias="SPREADSHEET_MAX_TEXT_CELL_CHARACTERS",
    )
    spreadsheet_preview_row_count: int = Field(
        default=5,
        ge=0,
        validation_alias="SPREADSHEET_PREVIEW_ROW_COUNT",
    )


@cache
def get_settings() -> Settings:
    """Return cached application settings."""

    return Settings()


__all__ = ["Settings", "get_settings"]
