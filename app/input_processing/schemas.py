"""Input Processor request and internal result schemas."""

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Attachment(BaseModel):
    """Transient uploaded attachment bytes for input processing."""

    model_config = ConfigDict(extra="forbid", strict=True)

    filename: str
    media_type: str
    content: bytes

    @field_validator("filename", "media_type")
    @classmethod
    def validate_non_empty_text(cls, value: str) -> str:
        """Reject missing-looking attachment metadata early."""
        if not value.strip():
            raise ValueError("must not be empty")
        return value

    @field_validator("content")
    @classmethod
    def validate_non_empty_content(cls, value: bytes) -> bytes:
        """Reject attachments with no bytes to process."""
        if not value:
            raise ValueError("must not be empty")
        return value


class InputRequest(BaseModel):
    """Public Input Processor request independent of API upload objects."""

    model_config = ConfigDict(extra="forbid", strict=True)

    user_query: str | None = None
    attachments: list[Attachment] = Field(default_factory=list)

    @field_validator("user_query")
    @classmethod
    def normalize_blank_user_query(cls, value: str | None) -> str | None:
        """Treat blank text as absent without inventing a question."""
        if value is None:
            return None
        if not value.strip():
            return None
        return value


__all__ = ["Attachment", "InputRequest"]
