"""Input validation tests for the Input Processor."""

from io import BytesIO
from pathlib import Path

import pytest
from pypdf import PdfWriter

from app.input_processing.errors import InputProcessingError, InputProcessingErrorCode
from app.input_processing.schemas import (
    Attachment,
    InputModality,
    InputRequest,
    ValidatedAttachment,
)
from guardrails.input_processor import (
    InputGuardrailDecision,
    MAX_ATTACHMENT_SIZE_BYTES,
    MAX_PDF_PAGE_COUNT,
    SUPPORTED_MEDIA_TYPES,
    get_pdf_page_count,
    has_jpeg_signature,
    has_pdf_signature,
    has_png_signature,
    inspect_attachment_signature,
    validate_attachment_modality,
    validate_attachment_size,
    validate_input_presence,
    validate_pdf_page_count,
    validate_supported_media_type,
)


PNG_BYTES = b"\x89PNG\r\n\x1a\nsynthetic image bytes"
JPEG_BYTES = b"\xff\xd8\xff\xe0synthetic image bytes"


def make_pdf_bytes(page_count: int) -> bytes:
    writer = PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=72, height=72)
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


PDF_BYTES = make_pdf_bytes(1)
FIXTURE_ROOT = Path(__file__).parent / "fixtures"


def read_fixture(relative_path: str) -> bytes:
    return (FIXTURE_ROOT / relative_path).read_bytes()


def test_supported_media_type_set_contains_only_confirmed_upload_types() -> None:
    assert SUPPORTED_MEDIA_TYPES == {
        "image/png",
        "image/jpeg",
        "application/pdf",
    }


@pytest.mark.parametrize(
    ("filename", "media_type", "content", "expected_modality"),
    [
        ("sample.png", "image/png", PNG_BYTES, InputModality.PNG),
        ("sample.jpg", "image/jpeg", JPEG_BYTES, InputModality.JPEG),
        ("sample.jpeg", "image/jpeg", JPEG_BYTES, InputModality.JPEG),
        ("sample.pdf", "application/pdf", PDF_BYTES, InputModality.PDF),
    ],
)
def test_validate_supported_media_type_accepts_confirmed_types(
    filename: str,
    media_type: str,
    content: bytes,
    expected_modality: InputModality,
) -> None:
    attachment = Attachment(filename=filename, media_type=media_type, content=content)

    assert validate_supported_media_type(attachment) == expected_modality


@pytest.mark.parametrize(
    ("filename", "media_type"),
    [
        ("sample.gif", "image/gif"),
        ("sample.bmp", "image/bmp"),
        ("sample.svg", "image/svg+xml"),
        ("sample.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        ("sample.txt", "text/plain"),
        ("sample.zip", "application/zip"),
    ],
)
def test_validate_supported_media_type_rejects_unsupported_types(
    filename: str,
    media_type: str,
) -> None:
    attachment = Attachment(
        filename=filename,
        media_type=media_type,
        content=b"synthetic bytes",
    )

    with pytest.raises(InputProcessingError) as exc_info:
        validate_supported_media_type(attachment)

    assert exc_info.value.code == InputProcessingErrorCode.UNSUPPORTED_FORMAT
    assert exc_info.value.message == "This attachment type is not supported."


@pytest.mark.parametrize(
    ("relative_path", "media_type", "expected_modality"),
    [
        ("images/valid/fictional_form.png", "image/png", InputModality.PNG),
        ("images/valid/fictional_form.jpg", "image/jpeg", InputModality.JPEG),
        ("pdfs/text/one_page_fixture.pdf", "application/pdf", InputModality.PDF),
    ],
)
def test_validate_attachment_modality_accepts_synthetic_fixtures(
    relative_path: str,
    media_type: str,
    expected_modality: InputModality,
) -> None:
    attachment = Attachment(
        filename=Path(relative_path).name,
        media_type=media_type,
        content=read_fixture(relative_path),
    )

    validated = validate_attachment_modality(attachment)

    assert validated.modality == expected_modality


@pytest.mark.parametrize(
    ("relative_path", "media_type"),
    [
        ("images/invalid/not_an_image.png", "image/png"),
        ("images/invalid/not_an_image.jpg", "image/jpeg"),
        ("pdfs/invalid/not_a_pdf.pdf", "application/pdf"),
    ],
)
def test_validate_attachment_modality_rejects_invalid_synthetic_fixtures(
    relative_path: str,
    media_type: str,
) -> None:
    attachment = Attachment(
        filename=Path(relative_path).name,
        media_type=media_type,
        content=read_fixture(relative_path),
    )

    with pytest.raises(InputProcessingError) as exc_info:
        validate_attachment_modality(attachment)

    assert exc_info.value.code == InputProcessingErrorCode.SIGNATURE_MISMATCH


def test_validate_input_presence_accepts_text_only_request() -> None:
    request = InputRequest(user_query="What does this mean?")

    assert validate_input_presence(request) == InputGuardrailDecision.ALLOW


def test_validate_input_presence_accepts_attachment_only_request() -> None:
    request = InputRequest(
        attachments=[
            Attachment(
                filename="sample.pdf",
                media_type="application/pdf",
                content=PDF_BYTES,
            )
        ]
    )

    assert validate_input_presence(request) == InputGuardrailDecision.ALLOW
    assert request.user_query is None


def test_validate_input_presence_accepts_text_and_attachment_request() -> None:
    request = InputRequest(
        user_query="Please summarize this.",
        attachments=[
            Attachment(
                filename="sample.png",
                media_type="image/png",
                content=PNG_BYTES,
            )
        ],
    )

    assert validate_input_presence(request) == InputGuardrailDecision.ALLOW


@pytest.mark.parametrize("user_query", [None, "", "   "])
def test_validate_input_presence_rejects_empty_request(
    user_query: str | None,
) -> None:
    request = InputRequest(user_query=user_query)

    with pytest.raises(InputProcessingError) as exc_info:
        validate_input_presence(request)

    assert exc_info.value.code == InputProcessingErrorCode.INVALID_INPUT
    assert exc_info.value.message == "Provide a question, an attachment, or both."
    assert request.user_query is None


def make_png_attachment_with_size(size: int) -> Attachment:
    return Attachment(
        filename="sample.png",
        media_type="image/png",
        content=PNG_BYTES + (b"x" * (size - len(PNG_BYTES))),
    )


def test_validate_attachment_size_accepts_below_limit() -> None:
    attachment = make_png_attachment_with_size(MAX_ATTACHMENT_SIZE_BYTES - 1)

    assert validate_attachment_size(attachment) == InputGuardrailDecision.ALLOW


def test_validate_attachment_size_rejects_at_limit() -> None:
    attachment = make_png_attachment_with_size(MAX_ATTACHMENT_SIZE_BYTES)

    with pytest.raises(InputProcessingError) as exc_info:
        validate_attachment_size(attachment)

    assert exc_info.value.code == InputProcessingErrorCode.FILE_TOO_LARGE
    assert exc_info.value.message == (
        "This attachment is too large. Upload a file smaller than 10 MB."
    )


def test_validate_attachment_size_rejects_above_limit() -> None:
    attachment = make_png_attachment_with_size(MAX_ATTACHMENT_SIZE_BYTES + 1)

    with pytest.raises(InputProcessingError) as exc_info:
        validate_attachment_size(attachment)

    assert exc_info.value.code == InputProcessingErrorCode.FILE_TOO_LARGE


def test_get_pdf_page_count_returns_page_count_from_bytes() -> None:
    assert get_pdf_page_count(make_pdf_bytes(3)) == 3


def test_get_pdf_page_count_wraps_unreadable_pdf_safely() -> None:
    with pytest.raises(InputProcessingError) as exc_info:
        get_pdf_page_count(b"%PDF-1.4\nnot a readable pdf\n%%EOF")

    assert exc_info.value.code == InputProcessingErrorCode.UNREADABLE_CONTENT
    assert exc_info.value.message == "This PDF could not be read for validation."


def test_validate_pdf_page_count_accepts_below_limit() -> None:
    attachment = Attachment(
        filename="sample.pdf",
        media_type="application/pdf",
        content=make_pdf_bytes(MAX_PDF_PAGE_COUNT - 1),
    )

    assert validate_pdf_page_count(attachment) == InputGuardrailDecision.ALLOW


def test_validate_pdf_page_count_accepts_at_limit() -> None:
    attachment = Attachment(
        filename="sample.pdf",
        media_type="application/pdf",
        content=make_pdf_bytes(MAX_PDF_PAGE_COUNT),
    )

    assert validate_pdf_page_count(attachment) == InputGuardrailDecision.ALLOW


def test_validate_pdf_page_count_rejects_above_limit() -> None:
    attachment = Attachment(
        filename="sample.pdf",
        media_type="application/pdf",
        content=make_pdf_bytes(MAX_PDF_PAGE_COUNT + 1),
    )

    with pytest.raises(InputProcessingError) as exc_info:
        validate_pdf_page_count(attachment)

    assert exc_info.value.code == InputProcessingErrorCode.PDF_PAGE_LIMIT_EXCEEDED
    assert exc_info.value.message == (
        f"This PDF has too many pages. Upload a PDF with {MAX_PDF_PAGE_COUNT} pages or fewer."
    )


def test_validate_attachment_modality_rejects_oversized_file_before_signature() -> None:
    attachment = Attachment(
        filename="sample.png",
        media_type="image/png",
        content=b"x" * MAX_ATTACHMENT_SIZE_BYTES,
    )

    with pytest.raises(InputProcessingError) as exc_info:
        validate_attachment_modality(attachment)

    assert exc_info.value.code == InputProcessingErrorCode.FILE_TOO_LARGE


def test_png_signature_validation_accepts_only_png_header() -> None:
    assert has_png_signature(PNG_BYTES) is True
    assert has_png_signature(b"not png bytes") is False


def test_jpeg_signature_validation_accepts_only_jpeg_header() -> None:
    assert has_jpeg_signature(JPEG_BYTES) is True
    assert has_jpeg_signature(b"not jpeg bytes") is False


def test_pdf_signature_validation_requires_header_and_eof_marker() -> None:
    assert has_pdf_signature(PDF_BYTES) is True
    assert has_pdf_signature(b"%PDF-1.4\nmissing eof marker") is False
    assert has_pdf_signature(b"not pdf bytes\n%%EOF") is False


@pytest.mark.parametrize(
    ("content", "expected_modality"),
    [
        (PNG_BYTES, InputModality.PNG),
        (JPEG_BYTES, InputModality.JPEG),
        (PDF_BYTES, InputModality.PDF),
    ],
)
def test_inspect_attachment_signature_identifies_supported_modalities(
    content: bytes,
    expected_modality: InputModality,
) -> None:
    assert inspect_attachment_signature(content) == expected_modality


def test_inspect_attachment_signature_returns_none_for_unknown_bytes() -> None:
    assert inspect_attachment_signature(b"not a supported file") is None


@pytest.mark.parametrize(
    "content",
    [
        b"%PDF-1.4\nmissing eof marker",
        b"not pdf bytes\n%%EOF",
        b"\x89PNX\r\n\x1a\nnear png bytes",
        b"\xff\xd9\xff\xe0near jpeg bytes",
    ],
)
def test_inspect_attachment_signature_rejects_obvious_invalid_signatures(
    content: bytes,
) -> None:
    assert inspect_attachment_signature(content) is None


@pytest.mark.parametrize(
    ("filename", "media_type", "content", "expected_modality"),
    [
        ("sample.png", "image/png", PNG_BYTES, InputModality.PNG),
        ("sample.jpg", "image/jpeg", JPEG_BYTES, InputModality.JPEG),
        ("sample.jpeg", "image/jpeg", JPEG_BYTES, InputModality.JPEG),
        ("sample.pdf", "application/pdf", PDF_BYTES, InputModality.PDF),
    ],
)
def test_validate_attachment_modality_returns_validated_attachment(
    filename: str,
    media_type: str,
    content: bytes,
    expected_modality: InputModality,
) -> None:
    attachment = Attachment(filename=filename, media_type=media_type, content=content)

    validated = validate_attachment_modality(attachment)

    assert isinstance(validated, ValidatedAttachment)
    assert validated.attachment == attachment
    assert validated.modality == expected_modality


def test_validate_attachment_modality_rejects_declared_pdf_with_image_bytes() -> None:
    attachment = Attachment(
        filename="sample.pdf",
        media_type="application/pdf",
        content=PNG_BYTES,
    )

    with pytest.raises(InputProcessingError) as exc_info:
        validate_attachment_modality(attachment)

    assert exc_info.value.code == InputProcessingErrorCode.SIGNATURE_MISMATCH
    assert exc_info.value.message == (
        "The declared file type does not match the uploaded content."
    )


def test_validate_attachment_modality_rejects_declared_image_with_pdf_bytes() -> None:
    attachment = Attachment(
        filename="sample.png",
        media_type="image/png",
        content=PDF_BYTES,
    )

    with pytest.raises(InputProcessingError) as exc_info:
        validate_attachment_modality(attachment)

    assert exc_info.value.code == InputProcessingErrorCode.SIGNATURE_MISMATCH


def test_validate_attachment_modality_rejects_over_page_limit_pdf() -> None:
    attachment = Attachment(
        filename="sample.pdf",
        media_type="application/pdf",
        content=make_pdf_bytes(MAX_PDF_PAGE_COUNT + 1),
    )

    with pytest.raises(InputProcessingError) as exc_info:
        validate_attachment_modality(attachment)

    assert exc_info.value.code == InputProcessingErrorCode.PDF_PAGE_LIMIT_EXCEEDED


@pytest.mark.parametrize(
    ("filename", "media_type", "content"),
    [
        ("sample.png", "image/png", b"not image bytes"),
        ("sample.jpg", "image/jpeg", b"not image bytes"),
        ("sample.pdf", "application/pdf", b"%PDF-1.4\nmissing eof marker"),
    ],
)
def test_validate_attachment_modality_rejects_declared_type_with_invalid_bytes(
    filename: str,
    media_type: str,
    content: bytes,
) -> None:
    attachment = Attachment(filename=filename, media_type=media_type, content=content)

    with pytest.raises(InputProcessingError) as exc_info:
        validate_attachment_modality(attachment)

    assert exc_info.value.code == InputProcessingErrorCode.SIGNATURE_MISMATCH


def test_validate_attachment_modality_does_not_trust_filename_extension() -> None:
    attachment = Attachment(
        filename="sample.pdf",
        media_type="image/png",
        content=PNG_BYTES,
    )

    validated = validate_attachment_modality(attachment)

    assert validated.modality == InputModality.PNG


def test_validate_attachment_modality_rejects_unknown_declared_media_type() -> None:
    attachment = Attachment(
        filename="sample.gif",
        media_type="image/gif",
        content=b"GIF89a synthetic bytes",
    )

    with pytest.raises(InputProcessingError) as exc_info:
        validate_attachment_modality(attachment)

    assert exc_info.value.code == InputProcessingErrorCode.UNSUPPORTED_FORMAT
