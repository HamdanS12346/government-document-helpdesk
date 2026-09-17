"""Spreadsheet-specific input processing boundary."""

from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.contracts.normalized_input import SpreadsheetContent
from app.input_processing.errors import InputProcessingErrorCode
from app.input_processing.schemas import (
    AttachmentProcessingError,
    InputModality,
    ValidatedAttachment,
)


class SpreadsheetInspectionStatus(StrEnum):
    """Provider-independent spreadsheet inspection outcomes."""

    SUCCESS = "success"
    EXTRACTION_FAILURE = "extraction_failure"
    UNAVAILABLE = "unavailable"
    TIMEOUT = "timeout"
    MALFORMED_RESPONSE = "malformed_response"
    CORRUPT_WORKBOOK = "corrupt_workbook"
    UNSUPPORTED_PROTECTION = "unsupported_protection"


class ParsedWorksheet(BaseModel):
    """Provider-independent worksheet inspection summary."""

    model_config = ConfigDict(extra="forbid", strict=True)

    name: str
    position: int = Field(ge=1)
    visible: bool = True
    max_row: int = Field(ge=0)
    max_column: int = Field(ge=0)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("worksheet name must not be empty")
        return value


class ParsedWorkbook(BaseModel):
    """Provider-independent workbook inspection result."""

    model_config = ConfigDict(extra="forbid", strict=True)

    filename: str
    worksheets: list[ParsedWorksheet] = Field(default_factory=list)

    @field_validator("filename")
    @classmethod
    def validate_filename(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("filename must not be empty")
        return value


class SpreadsheetInspectionResult(BaseModel):
    """Provider-independent spreadsheet parser result."""

    model_config = ConfigDict(extra="forbid", strict=True)

    status: SpreadsheetInspectionStatus
    workbook: ParsedWorkbook | None = None
    message: str | None = None

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("message must not be empty")
        return value

    @model_validator(mode="after")
    def validate_status_shape(self) -> "SpreadsheetInspectionResult":
        if self.status == SpreadsheetInspectionStatus.SUCCESS:
            if self.workbook is None:
                raise ValueError("successful spreadsheet inspection requires workbook")
            if self.message is not None:
                raise ValueError("successful spreadsheet inspection cannot include message")
            return self

        if self.workbook is not None:
            raise ValueError("failed spreadsheet inspection cannot include workbook")
        if self.message is None:
            raise ValueError("failed spreadsheet inspection requires a safe message")
        return self


class SpreadsheetProcessingResult(BaseModel):
    """Spreadsheet processor outcome with normalized content or safe failure."""

    model_config = ConfigDict(extra="forbid", strict=True)

    spreadsheet_content: SpreadsheetContent | None = None
    inspection_result: SpreadsheetInspectionResult | None = None
    error: AttachmentProcessingError | None = None

    @model_validator(mode="after")
    def validate_result_shape(self) -> "SpreadsheetProcessingResult":
        populated_fields = [
            self.spreadsheet_content is not None,
            self.inspection_result is not None,
            self.error is not None,
        ]
        if sum(populated_fields) != 1:
            raise ValueError(
                "spreadsheet processing result requires exactly one outcome field"
            )
        return self


class SpreadsheetParser(Protocol):
    """Narrow replaceable spreadsheet inspection capability."""

    def inspect(self, content: bytes, filename: str) -> SpreadsheetInspectionResult:
        """Inspect supported spreadsheet content from transient bytes."""


class PendingSpreadsheetParser:
    """Placeholder spreadsheet parser until the concrete provider is wired."""

    def inspect(self, content: bytes, filename: str) -> SpreadsheetInspectionResult:
        """Return a controlled unavailable outcome without exposing provider details."""

        return SpreadsheetInspectionResult(
            status=SpreadsheetInspectionStatus.UNAVAILABLE,
            message="Spreadsheet parser is not configured.",
        )


def inspect_spreadsheet_workbook(
    *,
    content: bytes,
    filename: str,
    parser: SpreadsheetParser,
) -> SpreadsheetInspectionResult:
    """Inspect a workbook through a controlled parser boundary."""

    try:
        result = parser.inspect(content, filename)
    except Exception:
        return SpreadsheetInspectionResult(
            status=SpreadsheetInspectionStatus.EXTRACTION_FAILURE,
            message="Spreadsheet content could not be inspected.",
        )

    if not isinstance(result, SpreadsheetInspectionResult):
        return SpreadsheetInspectionResult(
            status=SpreadsheetInspectionStatus.MALFORMED_RESPONSE,
            message="Spreadsheet parser returned an invalid result.",
        )

    return result


def process_spreadsheet_attachment(
    validated_attachment: ValidatedAttachment,
    parser: SpreadsheetParser,
) -> SpreadsheetProcessingResult:
    """Process an already-validated spreadsheet through the parser boundary."""

    attachment = validated_attachment.attachment
    if validated_attachment.modality != InputModality.XLSX:
        return SpreadsheetProcessingResult(
            error=AttachmentProcessingError(
                filename=attachment.filename,
                code=InputProcessingErrorCode.UNSUPPORTED_FORMAT,
                message="This attachment is not a supported spreadsheet.",
            )
        )

    inspection = inspect_spreadsheet_workbook(
        content=attachment.content,
        filename=attachment.filename,
        parser=parser,
    )
    if inspection.status == SpreadsheetInspectionStatus.SUCCESS:
        return SpreadsheetProcessingResult(inspection_result=inspection)

    return SpreadsheetProcessingResult(
        error=AttachmentProcessingError(
            filename=attachment.filename,
            code=_error_code_for_inspection_status(inspection.status),
            message=inspection.message or "Spreadsheet content could not be processed.",
        )
    )


def _error_code_for_inspection_status(
    status: SpreadsheetInspectionStatus,
) -> InputProcessingErrorCode:
    if status == SpreadsheetInspectionStatus.UNSUPPORTED_PROTECTION:
        return InputProcessingErrorCode.UNSUPPORTED_WORKBOOK_PROTECTION
    if status in {
        SpreadsheetInspectionStatus.CORRUPT_WORKBOOK,
        SpreadsheetInspectionStatus.MALFORMED_RESPONSE,
    }:
        return InputProcessingErrorCode.UNREADABLE_CONTENT
    return InputProcessingErrorCode.EXTRACTION_FAILURE


__all__ = [
    "ParsedWorkbook",
    "ParsedWorksheet",
    "PendingSpreadsheetParser",
    "SpreadsheetInspectionResult",
    "SpreadsheetInspectionStatus",
    "SpreadsheetParser",
    "SpreadsheetProcessingResult",
    "inspect_spreadsheet_workbook",
    "process_spreadsheet_attachment",
]
