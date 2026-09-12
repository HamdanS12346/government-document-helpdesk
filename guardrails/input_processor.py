"""Input Processor validation and safety guardrail boundary."""

from enum import StrEnum

from app.input_processing.errors import InputProcessingError, InputProcessingErrorCode
from app.input_processing.schemas import Attachment, InputModality, ValidatedAttachment


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
JPEG_SIGNATURE = b"\xff\xd8\xff"
PDF_SIGNATURE = b"%PDF-"

MEDIA_TYPE_MODALITIES = {
    "image/png": InputModality.PNG,
    "image/jpeg": InputModality.JPEG,
    "application/pdf": InputModality.PDF,
}


class InputGuardrailDecision(StrEnum):
    """Conceptual guardrail outcomes for Input Processor checks."""

    ALLOW = "allow"
    MASK_AND_CONTINUE = "mask_and_continue"
    REJECT = "reject"
    FAIL = "fail"


def validate_pre_processing_boundary() -> InputGuardrailDecision:
    """Placeholder for structure, media type, signature, size, and page checks."""

    return InputGuardrailDecision.ALLOW


def validate_post_extraction_boundary() -> InputGuardrailDecision:
    """Placeholder for PII masking and document-content safety checks."""

    return InputGuardrailDecision.ALLOW


def inspect_attachment_signature(content: bytes) -> InputModality | None:
    """Identify an attachment modality from its bytes."""

    if content.startswith(PNG_SIGNATURE):
        return InputModality.PNG
    if content.startswith(JPEG_SIGNATURE):
        return InputModality.JPEG
    if content.startswith(PDF_SIGNATURE):
        return InputModality.PDF
    return None


def validate_attachment_modality(attachment: Attachment) -> ValidatedAttachment:
    """Validate declared media type against the attachment byte signature."""

    declared_modality = MEDIA_TYPE_MODALITIES.get(attachment.media_type)
    if declared_modality is None:
        raise InputProcessingError(
            InputProcessingErrorCode.UNSUPPORTED_FORMAT,
            "This attachment type is not supported.",
        )

    actual_modality = inspect_attachment_signature(attachment.content)
    if actual_modality != declared_modality:
        raise InputProcessingError(
            InputProcessingErrorCode.SIGNATURE_MISMATCH,
            "The declared file type does not match the uploaded content.",
        )

    return ValidatedAttachment(attachment=attachment, modality=declared_modality)


__all__ = [
    "InputGuardrailDecision",
    "inspect_attachment_signature",
    "validate_attachment_modality",
    "validate_post_extraction_boundary",
    "validate_pre_processing_boundary",
]
