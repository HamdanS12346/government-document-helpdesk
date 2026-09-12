"""Input validation tests for the Input Processor."""

import pytest

from app.input_processing.errors import InputProcessingError, InputProcessingErrorCode
from app.input_processing.schemas import (
    Attachment,
    InputModality,
    InputRequest,
    ValidatedAttachment,
)
from guardrails.input_processor import (
    InputGuardrailDecision,
    SUPPORTED_MEDIA_TYPES,
    inspect_attachment_signature,
    validate_attachment_modality,
    validate_input_presence,
    validate_supported_media_type,
)


PNG_BYTES = b"\x89PNG\r\n\x1a\nsynthetic image bytes"
JPEG_BYTES = b"\xff\xd8\xff\xe0synthetic image bytes"
PDF_BYTES = b"%PDF-1.4\nsynthetic pdf bytes"


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
