"""Cleanup lifecycle tests for the Input Processor."""

from pathlib import Path

import pytest

from app.input_processing import image_processor
from app.input_processing.errors import InputProcessingError, InputProcessingErrorCode
from app.input_processing.ocr_provider import OCRResult, OCRStatus
from app.input_processing.schemas import Attachment, InputModality, ValidatedAttachment
from guardrails.input_processor import PIIMaskingResult


FIXTURES = Path(__file__).parent / "fixtures"
VALID_IMAGE = FIXTURES / "images" / "valid" / "fictional_form.png"


class TrackedImage:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def __enter__(self) -> "TrackedImage":
        self.events.append("enter")
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.events.append("exit")

    def verify(self) -> None:
        self.events.append("verify")


class StaticOCRProvider:
    def __init__(self, result: OCRResult) -> None:
        self.result = result

    def extract_text(self, image_content: bytes) -> OCRResult:
        return self.result


class RaisingOCRProvider:
    def extract_text(self, image_content: bytes) -> OCRResult:
        raise RuntimeError("ocr failed")


class MalformedOCRProvider:
    def extract_text(self, image_content: bytes) -> object:
        return {"status": "success", "text": "not validated"}


def make_validated_image() -> ValidatedAttachment:
    return ValidatedAttachment(
        attachment=Attachment(
            filename="fictional_form.png",
            media_type="image/png",
            content=VALID_IMAGE.read_bytes(),
        ),
        modality=InputModality.PNG,
    )


def patch_tracked_image_open(
    monkeypatch: pytest.MonkeyPatch,
    events: list[str],
) -> None:
    monkeypatch.setattr(
        image_processor.Image,
        "open",
        lambda stream: TrackedImage(events),
    )


def test_image_handle_is_closed_after_success(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[str] = []
    patch_tracked_image_open(monkeypatch, events)

    result = image_processor.process_image_attachment(
        make_validated_image(),
        StaticOCRProvider(OCRResult(status=OCRStatus.SUCCESS, text="Readable text")),
    )

    assert result.image_content is not None
    assert events == ["enter", "verify", "exit"]


def test_image_handle_is_closed_after_ocr_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[str] = []
    patch_tracked_image_open(monkeypatch, events)

    result = image_processor.process_image_attachment(
        make_validated_image(),
        RaisingOCRProvider(),
    )

    assert result.error is not None
    assert result.error.code == InputProcessingErrorCode.OCR_FAILURE
    assert events == ["enter", "verify", "exit"]


def test_image_handle_is_closed_after_empty_ocr(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[str] = []
    patch_tracked_image_open(monkeypatch, events)

    result = image_processor.process_image_attachment(
        make_validated_image(),
        StaticOCRProvider(
            OCRResult(
                status=OCRStatus.EMPTY,
                message="No readable text was found in this image.",
            )
        ),
    )

    assert result.error is not None
    assert result.error.code == InputProcessingErrorCode.UNREADABLE_CONTENT
    assert events == ["enter", "verify", "exit"]


def test_image_handle_is_closed_after_malformed_provider_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    patch_tracked_image_open(monkeypatch, events)

    result = image_processor.process_image_attachment(
        make_validated_image(),
        MalformedOCRProvider(),
    )

    assert result.error is not None
    assert result.error.code == InputProcessingErrorCode.OCR_FAILURE
    assert result.error.message == "OCR provider returned an invalid result."
    assert events == ["enter", "verify", "exit"]


def test_image_handle_is_closed_after_pii_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[str] = []
    patch_tracked_image_open(monkeypatch, events)

    def raise_pii_failure(text: str) -> PIIMaskingResult:
        raise InputProcessingError(
            InputProcessingErrorCode.PII_PROCESSING_FAILURE,
            "PII processing could not be completed safely.",
        )

    monkeypatch.setattr(image_processor, "mask_pii_in_text", raise_pii_failure)

    result = image_processor.process_image_attachment(
        make_validated_image(),
        StaticOCRProvider(OCRResult(status=OCRStatus.SUCCESS, text="Sensitive text")),
    )

    assert result.error is not None
    assert result.error.code == InputProcessingErrorCode.PII_PROCESSING_FAILURE
    assert events == ["enter", "verify", "exit"]


def test_image_handle_is_closed_after_unexpected_post_processing_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    patch_tracked_image_open(monkeypatch, events)

    monkeypatch.setattr(
        image_processor,
        "mark_document_text_untrusted",
        lambda text: (_ for _ in ()).throw(RuntimeError("unexpected")),
    )

    result = image_processor.process_image_attachment(
        make_validated_image(),
        StaticOCRProvider(OCRResult(status=OCRStatus.SUCCESS, text="Readable text")),
    )

    assert result.error is not None
    assert result.error.code == InputProcessingErrorCode.INTERNAL_PROCESSING_ERROR
    assert result.error.message == "Image content could not be processed safely."
    assert events == ["enter", "verify", "exit"]
