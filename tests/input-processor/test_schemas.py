"""Schema contract tests for the Input Processor."""

import pytest
from pydantic import ValidationError

from app.contracts.normalized_input import NormalizedInput
from app.input_processing.schemas import (
    Attachment,
    AttachmentProcessingError,
    AttachmentProcessingStatus,
    AttachmentProcessingWarning,
    InputProcessingResult,
    InputRequest,
)


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


def make_normalized_input() -> NormalizedInput:
    return NormalizedInput(
        user_query="What does this mean?",
        image_content=[],
        pdf_content=[],
        combined_text="What does this mean?",
    )


def test_input_processing_result_accepts_full_success() -> None:
    result = InputProcessingResult(
        success=True,
        normalized_input=make_normalized_input(),
        attachment_statuses=[
            AttachmentProcessingStatus(filename="sample.pdf", status="success")
        ],
    )

    assert result.success is True
    assert result.normalized_input is not None
    assert result.attachment_statuses[0].status == "success"


def test_input_processing_result_accepts_partial_success() -> None:
    error = AttachmentProcessingError(
        filename="bad.pdf",
        code="EXTRACTION_FAILURE",
        message="This attachment could not be processed.",
    )

    result = InputProcessingResult(
        success=True,
        normalized_input=make_normalized_input(),
        attachment_statuses=[
            AttachmentProcessingStatus(filename="good.pdf", status="success"),
            AttachmentProcessingStatus(
                filename="bad.pdf",
                status="failed",
                error=error,
            ),
        ],
    )

    assert result.success is True
    assert result.normalized_input is not None
    assert [status.status for status in result.attachment_statuses] == [
        "success",
        "failed",
    ]


def test_input_processing_result_accepts_complete_failure() -> None:
    error = AttachmentProcessingError(
        filename="bad.pdf",
        code="UNREADABLE_CONTENT",
        message="No readable content could be extracted from this attachment.",
    )

    result = InputProcessingResult(
        success=False,
        attachment_statuses=[
            AttachmentProcessingStatus(
                filename="bad.pdf",
                status="failed",
                error=error,
            )
        ],
    )

    assert result.success is False
    assert result.normalized_input is None


def test_successful_result_requires_normalized_input() -> None:
    with pytest.raises(ValidationError):
        InputProcessingResult(success=True)


def test_failed_result_rejects_normalized_input() -> None:
    with pytest.raises(ValidationError):
        InputProcessingResult(
            success=False,
            normalized_input=make_normalized_input(),
        )


def test_failed_attachment_status_requires_error() -> None:
    with pytest.raises(ValidationError):
        AttachmentProcessingStatus(filename="bad.pdf", status="failed")


def test_successful_attachment_status_rejects_error() -> None:
    with pytest.raises(ValidationError):
        AttachmentProcessingStatus(
            filename="good.pdf",
            status="success",
            error=AttachmentProcessingError(
                filename="good.pdf",
                code="UNSUPPORTED_FORMAT",
                message="This file type is not supported.",
            ),
        )


def test_result_warnings_are_safe_structured_objects() -> None:
    warning = AttachmentProcessingWarning(
        filename="sample.pdf",
        code="LOW_TEXT_CONTENT",
        message="Only limited text was extracted from this attachment.",
    )

    result = InputProcessingResult(
        success=True,
        normalized_input=make_normalized_input(),
        warnings=[warning],
    )

    assert result.warnings == [warning]
