"""Input Processor validation and safety guardrail boundary."""

from enum import StrEnum
from io import BytesIO
import re
from typing import Protocol

from pypdf import PdfReader

from app.input_processing.errors import InputProcessingError, InputProcessingErrorCode
from app.input_processing.schemas import (
    Attachment,
    InputModality,
    InputRequest,
    ValidatedAttachment,
)


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
JPEG_SIGNATURE = b"\xff\xd8\xff"
PDF_SIGNATURE = b"%PDF-"
PDF_EOF_MARKER = b"%%EOF"
ONE_MEGABYTE = 1024 * 1024
MAX_ATTACHMENT_SIZE_BYTES = 10 * ONE_MEGABYTE
# Existing project requirement is 10 pages. Input Processor docs propose 5 pages;
# keep this configurable until the team resolves that decision-log discrepancy.
MAX_PDF_PAGE_COUNT = 10

MEDIA_TYPE_MODALITIES = {
    "image/png": InputModality.PNG,
    "image/jpeg": InputModality.JPEG,
    "application/pdf": InputModality.PDF,
}
SUPPORTED_MEDIA_TYPES = frozenset(MEDIA_TYPE_MODALITIES)
PII_MASK = "[REDACTED]"
PII_PATTERNS = (
    re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b"),
    re.compile(r"\b\d{4}[ -]?\d{4}[ -]?\d{4}\b"),
    re.compile(r"\b(?:\+91[- ]?)?[6-9]\d{9}\b"),
    re.compile(r"\b[\w.%+-]+@[\w.-]+\.[A-Za-z]{2,}\b"),
)
AI_DIRECTED_INSTRUCTION_PATTERNS = (
    re.compile(r"\bignore (?:all )?(?:previous|prior|above) instructions\b", re.I),
    re.compile(r"\breveal (?:the )?(?:system|developer) (?:prompt|instructions)\b", re.I),
    re.compile(r"\b(?:send|show|print|exfiltrate) (?:the )?(?:secret|api key|credentials?)\b", re.I),
)


class InputGuardrailDecision(StrEnum):
    """Conceptual guardrail outcomes for Input Processor checks."""

    ALLOW = "allow"
    MASK_AND_CONTINUE = "mask_and_continue"
    REJECT = "reject"
    FAIL = "fail"


class PIIMaskingResult:
    """Result of PII masking for extracted document text."""

    def __init__(self, text: str, decision: InputGuardrailDecision) -> None:
        self.text = text
        self.decision = decision


class UntrustedDocumentText:
    """Extracted document text represented as untrusted data."""

    def __init__(self, text: str, suspicious: bool) -> None:
        self.text = text
        self.suspicious = suspicious
        self.decision = InputGuardrailDecision.ALLOW


class PIIMasker(Protocol):
    """Interface for replaceable PII detection and masking providers."""

    def mask(self, text: str) -> PIIMaskingResult:
        """Return masked text and the guardrail decision."""


class RegexPIIMasker:
    """Deterministic placeholder PII masker until provider/taxonomy is finalized."""

    def mask(self, text: str) -> PIIMaskingResult:
        masked_text = text
        for pattern in PII_PATTERNS:
            masked_text = pattern.sub(PII_MASK, masked_text)

        decision = (
            InputGuardrailDecision.MASK_AND_CONTINUE
            if masked_text != text
            else InputGuardrailDecision.ALLOW
        )
        return PIIMaskingResult(text=masked_text, decision=decision)


def validate_pre_processing_boundary() -> InputGuardrailDecision:
    """Placeholder for structure, media type, signature, size, and page checks."""

    return InputGuardrailDecision.ALLOW


def validate_post_extraction_boundary() -> InputGuardrailDecision:
    """Placeholder for PII masking and document-content safety checks."""

    return InputGuardrailDecision.ALLOW


def mask_pii_in_text(
    text: str,
    masker: PIIMasker | None = None,
) -> PIIMaskingResult:
    """Mask detected PII in extracted text without treating failures as no-PII."""

    active_masker = masker or RegexPIIMasker()
    try:
        return active_masker.mask(text)
    except InputProcessingError:
        raise
    except Exception as exc:
        raise InputProcessingError(
            InputProcessingErrorCode.PII_PROCESSING_FAILURE,
            "PII processing could not be completed safely.",
        ) from exc


def mark_document_text_untrusted(text: str) -> UntrustedDocumentText:
    """Represent extracted document text as data, not executable instructions."""

    suspicious = any(
        pattern.search(text) is not None
        for pattern in AI_DIRECTED_INSTRUCTION_PATTERNS
    )
    return UntrustedDocumentText(text=text, suspicious=suspicious)


def validate_input_presence(request: InputRequest) -> InputGuardrailDecision:
    """Require at least one usable input source before processing."""

    if request.user_query is not None or request.attachments:
        return InputGuardrailDecision.ALLOW

    raise InputProcessingError(
        InputProcessingErrorCode.INVALID_INPUT,
        "Provide a question, an attachment, or both.",
    )


def has_png_signature(content: bytes) -> bool:
    """Return whether bytes have the PNG file signature."""

    return content.startswith(PNG_SIGNATURE)


def has_jpeg_signature(content: bytes) -> bool:
    """Return whether bytes have the JPEG file signature."""

    return content.startswith(JPEG_SIGNATURE)


def has_pdf_signature(content: bytes) -> bool:
    """Return whether bytes look enough like a PDF for cheap validation."""

    return content.startswith(PDF_SIGNATURE) and PDF_EOF_MARKER in content[-1024:]


def inspect_attachment_signature(content: bytes) -> InputModality | None:
    """Identify an attachment modality from its bytes."""

    if has_png_signature(content):
        return InputModality.PNG
    if has_jpeg_signature(content):
        return InputModality.JPEG
    if has_pdf_signature(content):
        return InputModality.PDF
    return None


def validate_supported_media_type(attachment: Attachment) -> InputModality:
    """Validate the declared media type before modality-specific processing."""

    declared_modality = MEDIA_TYPE_MODALITIES.get(attachment.media_type)
    if declared_modality is None:
        raise InputProcessingError(
            InputProcessingErrorCode.UNSUPPORTED_FORMAT,
            "This attachment type is not supported.",
        )
    return declared_modality


def validate_attachment_size(attachment: Attachment) -> InputGuardrailDecision:
    """Enforce the confirmed upload requirement: file size must be below 10 MB."""

    if len(attachment.content) < MAX_ATTACHMENT_SIZE_BYTES:
        return InputGuardrailDecision.ALLOW

    raise InputProcessingError(
        InputProcessingErrorCode.FILE_TOO_LARGE,
        "This attachment is too large. Upload a file smaller than 10 MB.",
    )


def get_pdf_page_count(content: bytes) -> int:
    """Return the page count for a PDF from transient bytes."""

    try:
        reader = PdfReader(BytesIO(content))
        return len(reader.pages)
    except Exception as exc:
        raise InputProcessingError(
            InputProcessingErrorCode.UNREADABLE_CONTENT,
            "This PDF could not be read for validation.",
        ) from exc


def validate_pdf_page_count(attachment: Attachment) -> InputGuardrailDecision:
    """Reject PDFs that exceed the configured page limit before processing."""

    page_count = get_pdf_page_count(attachment.content)
    if page_count <= MAX_PDF_PAGE_COUNT:
        return InputGuardrailDecision.ALLOW

    raise InputProcessingError(
        InputProcessingErrorCode.PDF_PAGE_LIMIT_EXCEEDED,
        f"This PDF has too many pages. Upload a PDF with {MAX_PDF_PAGE_COUNT} pages or fewer.",
    )


def validate_attachment_modality(attachment: Attachment) -> ValidatedAttachment:
    """Validate declared media type against the attachment byte signature."""

    validate_attachment_size(attachment)
    declared_modality = validate_supported_media_type(attachment)
    actual_modality = inspect_attachment_signature(attachment.content)
    if actual_modality != declared_modality:
        raise InputProcessingError(
            InputProcessingErrorCode.SIGNATURE_MISMATCH,
            "The declared file type does not match the uploaded content.",
        )
    if declared_modality == InputModality.PDF:
        validate_pdf_page_count(attachment)

    return ValidatedAttachment(attachment=attachment, modality=declared_modality)


__all__ = [
    "InputGuardrailDecision",
    "MAX_ATTACHMENT_SIZE_BYTES",
    "MAX_PDF_PAGE_COUNT",
    "PIIMasker",
    "PIIMaskingResult",
    "RegexPIIMasker",
    "SUPPORTED_MEDIA_TYPES",
    "UntrustedDocumentText",
    "get_pdf_page_count",
    "has_jpeg_signature",
    "has_pdf_signature",
    "has_png_signature",
    "inspect_attachment_signature",
    "mark_document_text_untrusted",
    "mask_pii_in_text",
    "validate_attachment_size",
    "validate_attachment_modality",
    "validate_input_presence",
    "validate_pdf_page_count",
    "validate_post_extraction_boundary",
    "validate_pre_processing_boundary",
    "validate_supported_media_type",
]
