"""PDF-specific input processing boundary."""

from enum import StrEnum
from io import BytesIO
from typing import Protocol

from pypdf import PdfReader
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.input_processing.errors import InputProcessingError, InputProcessingErrorCode
from app.input_processing.schemas import (
    AttachmentProcessingError,
    InputModality,
    ValidatedAttachment,
)


# Existing project requirement is 10 pages. Input Processor docs propose 5 pages;
# keep this single configurable value until the team resolves that discrepancy.
MAX_PDF_PAGE_COUNT = 10


class PDFDocumentType(StrEnum):
    """Internal PDF content classifications."""

    TEXT_BASED = "text_based"
    SCANNED = "scanned"
    MIXED = "mixed"


class PDFExtractionStatus(StrEnum):
    """Provider-independent PDF inspection/extraction outcomes."""

    SUCCESS = "success"
    EXTRACTION_FAILURE = "extraction_failure"
    UNAVAILABLE = "unavailable"
    TIMEOUT = "timeout"
    MALFORMED_RESPONSE = "malformed_response"
    CORRUPT_PDF = "corrupt_pdf"


class PDFPageText(BaseModel):
    """Provider-independent text extracted for one PDF page."""

    model_config = ConfigDict(extra="forbid", strict=True)

    page_number: int
    text: str = ""

    @field_validator("page_number")
    @classmethod
    def validate_page_number(cls, value: int) -> int:
        if value < 1:
            raise ValueError("page_number must be 1 or greater")
        return value


class PDFExtractionResult(BaseModel):
    """Provider-independent PDF extraction result."""

    model_config = ConfigDict(extra="forbid", strict=True)

    status: PDFExtractionStatus
    document_type: PDFDocumentType | None = None
    pages: list[PDFPageText] = Field(default_factory=list)
    message: str | None = None

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("message must not be empty")
        return value

    @model_validator(mode="after")
    def validate_status_shape(self) -> "PDFExtractionResult":
        if self.status == PDFExtractionStatus.SUCCESS:
            if self.document_type is None:
                raise ValueError("successful PDF extraction requires document_type")
            if not self.pages:
                raise ValueError("successful PDF extraction requires page results")
            return self

        if self.document_type is not None or self.pages:
            raise ValueError("failed PDF extraction cannot include extracted content")
        if self.message is None:
            raise ValueError("failed PDF extraction requires a safe message")
        return self


class PDFClassificationResult(BaseModel):
    """Internal PDF classification from machine-readable page inspection."""

    model_config = ConfigDict(extra="forbid", strict=True)

    document_type: PDFDocumentType
    pages: list[PDFPageText]

    @model_validator(mode="after")
    def validate_pages_present(self) -> "PDFClassificationResult":
        if not self.pages:
            raise ValueError("PDF classification requires page results")
        return self


class PDFProcessingResult(BaseModel):
    """PDF processor outcome before normalized PDFContent is built."""

    model_config = ConfigDict(extra="forbid", strict=True)

    extraction_result: PDFExtractionResult | None = None
    error: AttachmentProcessingError | None = None

    @model_validator(mode="after")
    def validate_result_shape(self) -> "PDFProcessingResult":
        if (self.extraction_result is None) == (self.error is None):
            raise ValueError("PDF processing result requires extraction_result or error")
        return self


def classify_pdf_page_texts(page_texts: list[PDFPageText]) -> PDFDocumentType:
    """Classify a PDF from page-level machine-readable text presence."""

    if not page_texts:
        raise InputProcessingError(
            InputProcessingErrorCode.UNREADABLE_CONTENT,
            "This PDF could not be inspected for classification.",
        )

    has_text_by_page = [bool(page.text.strip()) for page in page_texts]
    if all(has_text_by_page):
        return PDFDocumentType.TEXT_BASED
    if not any(has_text_by_page):
        return PDFDocumentType.SCANNED
    return PDFDocumentType.MIXED


class PDFExtractor(Protocol):
    """Narrow replaceable PDF inspection/extraction capability."""

    def extract(self, pdf_content: bytes) -> PDFExtractionResult:
        """Inspect and extract supported PDF content from transient bytes."""


class PendingPDFExtractor:
    """Placeholder PDF extractor until the concrete provider is finalized."""

    def extract(self, pdf_content: bytes) -> PDFExtractionResult:
        """Return a controlled unavailable outcome without exposing provider details."""

        return PDFExtractionResult(
            status=PDFExtractionStatus.UNAVAILABLE,
            message="PDF extraction provider is not configured.",
        )


def get_pdf_page_count(pdf_content: bytes) -> int:
    """Return the page count for a PDF from transient bytes."""

    try:
        reader = PdfReader(BytesIO(pdf_content))
        return len(reader.pages)
    except Exception as exc:
        raise InputProcessingError(
            InputProcessingErrorCode.UNREADABLE_CONTENT,
            "This PDF could not be read for validation.",
        ) from exc


def classify_pdf_content(pdf_content: bytes) -> PDFClassificationResult:
    """Classify a PDF as text-based, scanned, or mixed using page text presence."""

    try:
        reader = PdfReader(BytesIO(pdf_content))
        pages = [
            PDFPageText(
                page_number=page_number,
                text=(page.extract_text() or "").strip(),
            )
            for page_number, page in enumerate(reader.pages, start=1)
        ]
    except Exception as exc:
        raise InputProcessingError(
            InputProcessingErrorCode.UNREADABLE_CONTENT,
            "This PDF could not be inspected for classification.",
        ) from exc

    return PDFClassificationResult(
        document_type=classify_pdf_page_texts(pages),
        pages=pages,
    )


def validate_pdf_page_count(
    pdf_content: bytes,
    *,
    max_page_count: int = MAX_PDF_PAGE_COUNT,
) -> None:
    """Reject PDFs that exceed the configured page limit before extraction/OCR."""

    if max_page_count <= 0:
        raise ValueError("max_page_count must be positive")

    page_count = get_pdf_page_count(pdf_content)
    if page_count <= max_page_count:
        return

    raise InputProcessingError(
        InputProcessingErrorCode.PDF_PAGE_LIMIT_EXCEEDED,
        f"This PDF has too many pages. Upload a PDF with {max_page_count} pages or fewer.",
    )


def process_pdf_attachment(
    validated_attachment: ValidatedAttachment,
    pdf_extractor: PDFExtractor,
    *,
    max_page_count: int = MAX_PDF_PAGE_COUNT,
) -> PDFProcessingResult:
    """Process an already-validated PDF through bounded PDF extraction."""

    attachment = validated_attachment.attachment
    if validated_attachment.modality != InputModality.PDF:
        return PDFProcessingResult(
            error=AttachmentProcessingError(
                filename=attachment.filename,
                code=InputProcessingErrorCode.UNSUPPORTED_FORMAT,
                message="This attachment is not a supported PDF.",
            )
        )

    try:
        validate_pdf_page_count(
            attachment.content,
            max_page_count=max_page_count,
        )
        classify_pdf_content(attachment.content)
    except InputProcessingError as exc:
        return PDFProcessingResult(
            error=AttachmentProcessingError(
                filename=attachment.filename,
                code=exc.code,
                message=exc.message,
            )
        )

    try:
        extraction_result = pdf_extractor.extract(attachment.content)
    except Exception:
        return PDFProcessingResult(
            error=AttachmentProcessingError(
                filename=attachment.filename,
                code=InputProcessingErrorCode.EXTRACTION_FAILURE,
                message="PDF extraction could not be completed.",
            )
        )

    if not isinstance(extraction_result, PDFExtractionResult):
        return PDFProcessingResult(
            error=AttachmentProcessingError(
                filename=attachment.filename,
                code=InputProcessingErrorCode.EXTRACTION_FAILURE,
                message="PDF extraction provider returned an invalid result.",
            )
        )

    return PDFProcessingResult(extraction_result=extraction_result)


__all__ = [
    "MAX_PDF_PAGE_COUNT",
    "PDFClassificationResult",
    "PDFDocumentType",
    "PDFExtractionResult",
    "PDFExtractionStatus",
    "PDFExtractor",
    "PDFPageText",
    "PDFProcessingResult",
    "PendingPDFExtractor",
    "classify_pdf_content",
    "classify_pdf_page_texts",
    "get_pdf_page_count",
    "process_pdf_attachment",
    "validate_pdf_page_count",
]
