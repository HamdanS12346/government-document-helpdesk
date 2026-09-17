"""Input Processor validation and safety guardrail boundary."""

from enum import StrEnum
from io import BytesIO
import re
from typing import Protocol
from zipfile import BadZipFile, ZipFile

from app.input_processing.errors import InputProcessingError, InputProcessingErrorCode
from app.input_processing.pdf_processor import (
    MAX_PDF_PAGE_COUNT,
    get_pdf_page_count,
    validate_pdf_page_count as validate_pdf_page_count_bytes,
)
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
ZIP_SIGNATURE = b"PK\x03\x04"
XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
XLSX_EXTENSION = ".xlsx"
XLSX_REQUIRED_PACKAGE_PARTS = frozenset(
    {
        "[Content_Types].xml",
        "xl/workbook.xml",
    }
)
ONE_MEGABYTE = 1024 * 1024
MAX_ATTACHMENT_SIZE_BYTES = 10 * ONE_MEGABYTE

MEDIA_TYPE_MODALITIES = {
    "image/png": InputModality.PNG,
    "image/jpeg": InputModality.JPEG,
    "application/pdf": InputModality.PDF,
    XLSX_MEDIA_TYPE: InputModality.XLSX,
}
SUPPORTED_MEDIA_TYPES = frozenset(MEDIA_TYPE_MODALITIES)
PII_MASK = "[REDACTED]"
PII_PATTERNS = (
    re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b"),
    re.compile(r"\b\d{4}[ -]?\d{4}[ -]?\d{4}\b"),
    re.compile(r"\b(?:\+91[- ]?)?[6-9]\d{9}\b"),
    re.compile(r"\b[\w.%+-]+@[\w.-]+\.[A-Za-z]{2,}\b"),
    # Voter ID / EPIC
    re.compile(r"\b[A-Z]{3}[0-9]{7}\b"),
    # Indian Passport Number (1 letter followed by 7 digits)
    re.compile(r"\b[A-Z][0-9]{7}\b"),
    # Indian Driving License
    re.compile(r"\b[A-Z]{2}[- ]?[0-9]{2}[- ]?[0-9]{4}[- ]?[0-9]{7}\b"),
    re.compile(r"\b[A-Z]{2}[0-9]{13,15}\b"),
    # IFSC Code
    re.compile(r"\b[A-Z]{4}0[A-Z0-9]{6}\b"),
    # Bank Account Numbers with label/prefix or standalone 13-18 digits
    re.compile(r"\b(?:A/C|Account(?:\s*No\.?)?|Bank\s*A/C)[\s:#-]*[0-9]{9,18}\b", re.I),
    re.compile(r"\b[0-9]{13,18}\b"),
)
AI_DIRECTED_INSTRUCTION_PATTERNS = (
    re.compile(r"\bignore (?:all )?(?:previous |prior |above )?instructions\b", re.I),
    re.compile(r"\breveal (?:the |your )?(?:system|developer) (?:prompt|instructions)\b", re.I),
    re.compile(r"\b(?:send|show|print|exfiltrate) (?:the |your )?(?:secret|api key|credentials?)\b", re.I),
)
USER_QUERY_INJECTION_PATTERNS = (
    re.compile(r"\bignore (?:all )?(?:previous |prior |above )?instructions\b", re.I),
    re.compile(r"\b(?:reveal|show|print|display) (?:the |your |all )?(?:system|developer|hidden) (?:prompt|instructions)\b", re.I),
    re.compile(r"\b(?:send|show|print|exfiltrate|leak) (?:the |your )?(?:secret|api key|credentials?|environment|env|token)\b", re.I),
    re.compile(r"\b(?:system override|jailbreak|bypass safety|developer mode)\b", re.I),
    re.compile(r"\byou are now in (?:DAN|unrestricted|jailbroken) mode\b", re.I),
    re.compile(r"\bdisregard (?:all )?(?:safety|guardrails?|guidelines?)\b", re.I),
)
PROFANITY_ABUSE_PATTERNS = (
    re.compile(r"\b(?:fuck|shit|bitch|bastard|asshole|cunt)\b", re.I),
    re.compile(r"\b(?:kill yourself|go to hell|die in a fire)\b", re.I),
    re.compile(r"\b(?:madarchod|bhenchod|chutiya|harami|bhosdike|kameena)\b", re.I),
)
ILLEGAL_PROCEDURE_PATTERNS = (
    # Bribery / Kickbacks / Speed money
    re.compile(r"\b(?:pay|paying|give|giving|offer|offering|take|taking|accept|arrange|demand)\s+(?:a\s+)?(?:bribe|kickback|speed\s+money|rishwat|ghoos|under\s+the\s+table\s+(?:money|cash)|chai\s*pani)\b", re.I),
    re.compile(r"\b(?:how\s+(?:to|can\s+I|much)|where\s+to|who\s+can)\b.*\b(?:bribe|pay\s+off|pay\s+a\s+bribe|pay\s+speed\s+money|rishwat|ghoos)\b", re.I),
    re.compile(r"\b(?:agent|dalal|middleman|broker)\s+(?:to|who\s+can|for)\s+(?:bribe|pay\s+bribe|speed\s+up\s+illegally)\b", re.I),
    re.compile(r"\b(?:bribe|pay\s+cash\s+to)\s+(?:for|to\s+pass)\s+(?:driving\s+test|passport|visa|ration\s+card|officer)\b", re.I),
    re.compile(r"\b(?:money|cash)\s+under\s+the\s+table\b", re.I),
    re.compile(r"\bchai\s*pani\b.*\b(?:clerk|officer|inspector|babu|official|permission|approval|license)\b", re.I),
    re.compile(r"\b(?:rishwat|ghoos)\b", re.I),
    # Tax / Duty / Statutory Evasion
    re.compile(r"\b(?:how\s+to|how\s+can\s+I|where\s+to)\s+(?:evade|avoid\s+paying|dodge)\s+(?:income\s+tax|gst|taxes?|tax|customs?\s+duty)\b", re.I),
    re.compile(r"\b(?:evade|evading)\s+(?:income\s+tax|gst|taxes?|tax|customs?\s+duty)\b", re.I),
    re.compile(r"\b(?:fake|bogus|counterfeit)\s+(?:gst\s+invoice|gst\s+bill|tax\s+invoice|billing)\b", re.I),
    re.compile(r"\b(?:hide|launder|convert)\s+(?:black\s+money|unaccounted\s+cash)\b", re.I),
    re.compile(r"\b(?:smuggle|smuggling)\b", re.I),
    # Document Forgery / Counterfeit / Illegal Procedural Bypasses
    re.compile(r"\b(?:make|create|buy|get|generate|provide|sell)\s+(?:a\s+)?(?:fake|counterfeit|forged)\s+(?:aadhaar|pan\s+card|passport|driving\s+licen[cs]e|voter\s+id|birth\s+certificate|caste\s+certificate|ration\s+card|certificate|degree|document)\b", re.I),
    re.compile(r"\b(?:fake|counterfeit|forged)\s+(?:aadhaar|pan\s+card|passport|driving\s+licen[cs]e|voter\s+id|birth\s+certificate|caste\s+certificate|ration\s+card|stamp|seal|signature)\b", re.I),
    re.compile(r"\b(?:forge|fabricate|falsify)\s+(?:a\s+)?(?:government\s+stamp|gazetted\s+officer\s+signature|seal|stamp|certificate)\b", re.I),
    re.compile(r"\b(?:bypass|skip|fake)\s+(?:police\s+verification|kyc\s+verification|biometrics?)\s+illegally\b", re.I),
    re.compile(r"\b(?:fake|counterfeit)\s+(?:aadhaar|pan\s+card|driving\s+licen[cs]e|passport)\s+(?:maker|generator|template)\b", re.I),
)
ANTI_CORRUPTION_REPORTING_PATTERNS = (
    re.compile(r"\b(?:report|complaint\s+against|file\s+a\s+complaint|whistleblower|helpline|vigilance|anti[- ]corruption\s+bureau|lokpal|cbi|cvc|acb|penalt(?:y|ies)\s+for|punishment\s+for|law\s+against)\b", re.I),
    re.compile(r"\b(?:section\s+80c|80d|tax\s+deduction|tax\s+exemption|tax\s+rebate|legal\s+tax\s+saving|save\s+tax\s+legally)\b", re.I),
)
SAFETY_REFUSAL_MESSAGE = (
    "This helpdesk cannot assist with requests involving bribery, tax evasion, "
    "document forgery, or bypassing official procedures. Please refer to official "
    "government portals for lawful guidelines."
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


MAX_IMAGE_PIXELS = 10_000_000


def validate_image_dimensions(content: bytes) -> InputGuardrailDecision:
    """Inspect image dimensions without full decompression to prevent memory bombs."""
    from io import BytesIO
    from PIL import Image, UnidentifiedImageError

    try:
        with Image.open(BytesIO(content)) as img:
            size = getattr(img, "size", None)
            if size is not None:
                width, height = size
                if width * height > MAX_IMAGE_PIXELS:
                    raise InputProcessingError(
                        InputProcessingErrorCode.FILE_TOO_LARGE,
                        f"Image resolution exceeds maximum allowed limit ({MAX_IMAGE_PIXELS} pixels).",
                    )
            return InputGuardrailDecision.ALLOW
    except InputProcessingError:
        raise
    except (UnidentifiedImageError, OSError) as exc:
        raise InputProcessingError(
            InputProcessingErrorCode.UNREADABLE_CONTENT,
            "This image could not be inspected safely.",
        ) from exc


def validate_user_query_safety(query: str) -> InputGuardrailDecision:
    """Actively reject user queries that attempt prompt injection or jailbreaking."""
    for pattern in USER_QUERY_INJECTION_PATTERNS:
        if pattern.search(query):
            raise InputProcessingError(
                InputProcessingErrorCode.SAFETY_REJECTION,
                "The request could not be processed because it contains unsupported instruction-like commands.",
            )
    return InputGuardrailDecision.ALLOW


def validate_content_civility(text: str) -> InputGuardrailDecision:
    """Detect abusive, profane, or threatening language and reject it."""
    for pattern in PROFANITY_ABUSE_PATTERNS:
        if pattern.search(text):
            raise InputProcessingError(
                InputProcessingErrorCode.SAFETY_REJECTION,
                "Please ensure questions are respectful and focused on government services and documents.",
            )
    return InputGuardrailDecision.ALLOW


def validate_safety_compliance(text: str) -> InputGuardrailDecision:
    """Detect and reject requests involving bribery, tax evasion, forgery, or illegal procedural shortcuts."""
    if not text:
        return InputGuardrailDecision.ALLOW

    # Allow benign reporting, complaint filing, whistleblowing, or legal tax deduction inquiries
    is_reporting = any(pat.search(text) for pat in ANTI_CORRUPTION_REPORTING_PATTERNS)
    if is_reporting:
        return InputGuardrailDecision.ALLOW

    for pattern in ILLEGAL_PROCEDURE_PATTERNS:
        if pattern.search(text):
            raise InputProcessingError(
                InputProcessingErrorCode.SAFETY_REJECTION,
                SAFETY_REFUSAL_MESSAGE,
            )
    return InputGuardrailDecision.ALLOW


def validate_pre_processing_boundary(request: InputRequest) -> InputGuardrailDecision:
    """Execute pre-processing boundary validation on the incoming request."""
    validate_input_presence(request)
    return InputGuardrailDecision.ALLOW


def validate_post_extraction_boundary(
    text: str,
    *,
    is_user_query: bool = False,
    strict_safety: bool = True,
    masker: PIIMasker | None = None,
) -> str:
    """Execute post-extraction boundary checks: civility, illegal/evasion safety, query safety, and PII masking."""
    validate_content_civility(text)
    validate_safety_compliance(text)
    if is_user_query and strict_safety:
        validate_user_query_safety(text)
    masked_result = mask_pii_in_text(text, masker=masker)
    return masked_result.text


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


def has_xlsx_signature(content: bytes) -> bool:
    """Return whether bytes look like a minimal Office Open XML workbook package."""

    if not content.startswith(ZIP_SIGNATURE):
        return False

    try:
        with ZipFile(BytesIO(content)) as archive:
            package_parts = set(archive.namelist())
    except (BadZipFile, OSError):
        return False

    return XLSX_REQUIRED_PACKAGE_PARTS.issubset(package_parts)


def inspect_attachment_signature(content: bytes) -> InputModality | None:
    """Identify an attachment modality from its bytes."""

    if has_png_signature(content):
        return InputModality.PNG
    if has_jpeg_signature(content):
        return InputModality.JPEG
    if has_pdf_signature(content):
        return InputModality.PDF
    if has_xlsx_signature(content):
        return InputModality.XLSX
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


def validate_xlsx_filename_extension(attachment: Attachment) -> InputGuardrailDecision:
    """Require `.xlsx` filenames for spreadsheet workbook uploads."""

    if attachment.filename.lower().endswith(XLSX_EXTENSION):
        return InputGuardrailDecision.ALLOW

    raise InputProcessingError(
        InputProcessingErrorCode.UNSUPPORTED_FORMAT,
        "Only .xlsx spreadsheet uploads are supported.",
    )


def validate_pdf_page_count(attachment: Attachment) -> InputGuardrailDecision:
    """Reject PDFs that exceed the configured page limit before processing."""

    validate_pdf_page_count_bytes(attachment.content)
    return InputGuardrailDecision.ALLOW


def validate_attachment_modality(attachment: Attachment) -> ValidatedAttachment:
    """Validate declared media type against the attachment byte signature."""

    validate_attachment_size(attachment)
    declared_modality = validate_supported_media_type(attachment)
    if declared_modality == InputModality.XLSX:
        validate_xlsx_filename_extension(attachment)
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
    "ANTI_CORRUPTION_REPORTING_PATTERNS",
    "ILLEGAL_PROCEDURE_PATTERNS",
    "InputGuardrailDecision",
    "MAX_ATTACHMENT_SIZE_BYTES",
    "MAX_IMAGE_PIXELS",
    "MAX_PDF_PAGE_COUNT",
    "PIIMasker",
    "PIIMaskingResult",
    "PROFANITY_ABUSE_PATTERNS",
    "RegexPIIMasker",
    "SAFETY_REFUSAL_MESSAGE",
    "SUPPORTED_MEDIA_TYPES",
    "XLSX_MEDIA_TYPE",
    "USER_QUERY_INJECTION_PATTERNS",
    "UntrustedDocumentText",
    "get_pdf_page_count",
    "has_jpeg_signature",
    "has_pdf_signature",
    "has_xlsx_signature",
    "has_png_signature",
    "inspect_attachment_signature",
    "mark_document_text_untrusted",
    "mask_pii_in_text",
    "validate_attachment_size",
    "validate_attachment_modality",
    "validate_content_civility",
    "validate_image_dimensions",
    "validate_input_presence",
    "validate_pdf_page_count",
    "validate_post_extraction_boundary",
    "validate_pre_processing_boundary",
    "validate_safety_compliance",
    "validate_supported_media_type",
    "validate_user_query_safety",
    "validate_xlsx_filename_extension",
]
