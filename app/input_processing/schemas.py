"""Input Processor request and internal result schemas."""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.contracts.normalized_input import NormalizedInput
from app.input_processing.errors import InputProcessingErrorCode, InputProcessingWarningCode


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


class InputModality(StrEnum):
    """Supported validated input modalities."""

    TEXT = "text"
    PNG = "png"
    JPEG = "jpeg"
    PDF = "pdf"
    XLSX = "xlsx"


class ValidatedAttachment(BaseModel):
    """Attachment after declared type and signature validation."""

    model_config = ConfigDict(extra="forbid", strict=True)

    attachment: Attachment
    modality: InputModality


AttachmentStatus = Literal["success", "failed"]


class AttachmentProcessingError(BaseModel):
    """Safe attachment-scoped processing error."""

    model_config = ConfigDict(extra="forbid", strict=True)

    filename: str
    code: InputProcessingErrorCode
    message: str

    @field_validator("filename", "message")
    @classmethod
    def validate_non_empty_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value


class AttachmentProcessingWarning(BaseModel):
    """Safe attachment-scoped processing warning."""

    model_config = ConfigDict(extra="forbid", strict=True)

    filename: str
    code: str
    message: str

    @field_validator("filename", "code", "message")
    @classmethod
    def validate_non_empty_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value


class AttachmentProcessingStatus(BaseModel):
    """Processing outcome for one attachment."""

    model_config = ConfigDict(extra="forbid", strict=True)

    filename: str
    status: AttachmentStatus
    error: AttachmentProcessingError | None = None
    warnings: list[AttachmentProcessingWarning] = Field(default_factory=list)

    @field_validator("filename")
    @classmethod
    def validate_non_empty_filename(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value

    @model_validator(mode="after")
    def validate_error_matches_status(self) -> "AttachmentProcessingStatus":
        if self.status == "failed" and self.error is None:
            raise ValueError("failed attachment status requires an error")
        if self.status == "success" and self.error is not None:
            raise ValueError("successful attachment status cannot include an error")
        return self


class InputProcessingResult(BaseModel):
    """Input Processor outcome with normalized content and safe statuses."""

    model_config = ConfigDict(extra="forbid", strict=True)

    success: bool
    normalized_input: NormalizedInput | None = None
    attachment_statuses: list[AttachmentProcessingStatus] = Field(default_factory=list)
    warnings: list[AttachmentProcessingWarning] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_success_shape(self) -> "InputProcessingResult":
        if self.success and self.normalized_input is None:
            raise ValueError("successful result requires normalized_input")
        if not self.success and self.normalized_input is not None:
            raise ValueError("failed result cannot include normalized_input")
        return self


__all__ = [
    "Attachment",
    "AttachmentProcessingError",
    "AttachmentProcessingStatus",
    "AttachmentProcessingWarning",
    "AttachmentStatus",
    "InputModality",
    "InputProcessingErrorCode",
    "InputProcessingWarningCode",
    "InputProcessingResult",
    "InputRequest",
    "ValidatedAttachment",
]
