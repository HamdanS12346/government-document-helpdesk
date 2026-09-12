"""Schema contract tests for the Input Processor."""

import pytest
from pydantic import ValidationError

from app.input_processing.schemas import Attachment, InputRequest


def test_attachment_accepts_transient_bytes() -> None:
    attachment = Attachment(
        filename="sample.pdf",
        media_type="application/pdf",
        content=b"%PDF-1.4",
    )

    assert attachment.filename == "sample.pdf"
    assert attachment.media_type == "application/pdf"
    assert attachment.content == b"%PDF-1.4"


@pytest.mark.parametrize(
    "payload",
    [
        {"media_type": "application/pdf", "content": b"%PDF-1.4"},
        {"filename": "sample.pdf", "content": b"%PDF-1.4"},
        {"filename": "sample.pdf", "media_type": "application/pdf"},
        {"filename": "", "media_type": "application/pdf", "content": b"%PDF-1.4"},
        {"filename": "sample.pdf", "media_type": " ", "content": b"%PDF-1.4"},
        {"filename": "sample.pdf", "media_type": "application/pdf", "content": b""},
    ],
)
def test_attachment_rejects_missing_or_empty_required_fields(payload: dict) -> None:
    with pytest.raises(ValidationError):
        Attachment.model_validate(payload)


def test_attachment_rejects_non_byte_content() -> None:
    with pytest.raises(ValidationError):
        Attachment(
            filename="sample.pdf",
            media_type="application/pdf",
            content="not bytes",
        )


def test_attachment_rejects_api_or_path_specific_fields() -> None:
    with pytest.raises(ValidationError):
        Attachment.model_validate(
            {
                "filename": "sample.pdf",
                "media_type": "application/pdf",
                "content": b"%PDF-1.4",
                "file_path": "C:/tmp/sample.pdf",
            }
        )


def test_input_request_accepts_text_only_request() -> None:
    request = InputRequest(user_query="What does this document mean?")

    assert request.user_query == "What does this document mean?"
    assert request.attachments == []


def test_input_request_accepts_attachment_only_request() -> None:
    attachment = Attachment(
        filename="sample.png",
        media_type="image/png",
        content=b"\x89PNG\r\n\x1a\n",
    )

    request = InputRequest(attachments=[attachment])

    assert request.user_query is None
    assert request.attachments == [attachment]


def test_input_request_normalizes_blank_user_query_to_absent() -> None:
    request = InputRequest(user_query="   ")

    assert request.user_query is None


def test_input_request_rejects_malformed_attachment_objects() -> None:
    with pytest.raises(ValidationError):
        InputRequest.model_validate(
            {
                "attachments": [
                    {
                        "filename": "sample.pdf",
                        "media_type": "application/pdf",
                        "content": b"%PDF-1.4",
                        "upload_file": object(),
                    }
                ]
            }
        )


def test_input_request_rejects_non_attachment_items() -> None:
    with pytest.raises(ValidationError):
        InputRequest.model_validate({"attachments": [b"%PDF-1.4"]})
