"""OCR provider boundary tests for the Input Processor."""

import pytest
from pydantic import ValidationError

from app.input_processing import ocr_provider
from app.input_processing.ocr_provider import (
    OCRProvider,
    OCRResult,
    OCRStatus,
    TesseractOCRProvider,
)


def test_ocr_result_accepts_successful_text_extraction() -> None:
    result = OCRResult(
        status=OCRStatus.SUCCESS,
        text="Application number ABC-123",
    )

    assert result.status == OCRStatus.SUCCESS
    assert result.text == "Application number ABC-123"
    assert result.message is None


def test_ocr_result_accepts_empty_extraction_outcome() -> None:
    result = OCRResult(
        status=OCRStatus.EMPTY,
        message="No readable text was found in this image.",
    )

    assert result.status == OCRStatus.EMPTY
    assert result.text == ""
    assert result.message == "No readable text was found in this image."


def test_ocr_result_accepts_low_confidence_unusable_text_outcome() -> None:
    result = OCRResult(
        status=OCRStatus.LOW_CONFIDENCE,
        text="A7 ~~ ??",
        message="OCR output was not reliable enough to use.",
    )

    assert result.status == OCRStatus.LOW_CONFIDENCE
    assert result.text == "A7 ~~ ??"
    assert result.message == "OCR output was not reliable enough to use."


@pytest.mark.parametrize(
    "status,message",
    [
        (OCRStatus.UNAVAILABLE, "OCR provider is unavailable."),
        (OCRStatus.PROVIDER_ERROR, "OCR provider could not process this image."),
    ],
)
def test_ocr_result_accepts_controlled_provider_failures(
    status: OCRStatus,
    message: str,
) -> None:
    result = OCRResult(status=status, message=message)

    assert result.status == status
    assert result.text == ""
    assert result.message == message


def test_successful_ocr_result_requires_extracted_text() -> None:
    with pytest.raises(ValidationError):
        OCRResult(status=OCRStatus.SUCCESS, text=" ")


def test_empty_ocr_result_rejects_fabricated_text() -> None:
    with pytest.raises(ValidationError):
        OCRResult(
            status=OCRStatus.EMPTY,
            text="This text should not be present.",
        )


@pytest.mark.parametrize("status", [OCRStatus.UNAVAILABLE, OCRStatus.PROVIDER_ERROR])
def test_provider_failure_result_rejects_extracted_text(status: OCRStatus) -> None:
    with pytest.raises(ValidationError):
        OCRResult(
            status=status,
            text="Text from a failed provider should not be trusted.",
            message="OCR provider could not process this image.",
        )


@pytest.mark.parametrize("status", [OCRStatus.UNAVAILABLE, OCRStatus.PROVIDER_ERROR])
def test_provider_failure_result_requires_safe_message(status: OCRStatus) -> None:
    with pytest.raises(ValidationError):
        OCRResult(status=status)


def test_ocr_result_rejects_malformed_provider_response_fields() -> None:
    with pytest.raises(ValidationError):
        OCRResult.model_validate(
            {
                "status": "success",
                "text": "Application number ABC-123",
                "raw_provider_payload": {"confidence": 91},
            }
        )


def test_ocr_result_rejects_unknown_status() -> None:
    with pytest.raises(ValidationError):
        OCRResult(status="timed_out", message="Timed out.")


def test_mock_provider_can_satisfy_narrow_provider_interface() -> None:
    class MockOCRProvider:
        def extract_text(self, image_content: bytes) -> OCRResult:
            assert image_content == b"synthetic-image"
            return OCRResult(status=OCRStatus.SUCCESS, text="Synthetic form text")

    provider: OCRProvider = MockOCRProvider()

    result = provider.extract_text(b"synthetic-image")

    assert result == OCRResult(status=OCRStatus.SUCCESS, text="Synthetic form text")


class FakeImage:
    def __enter__(self) -> "FakeImage":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None


def test_tesseract_provider_returns_successful_extracted_text(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_image = FakeImage()

    def fake_open(stream: object) -> FakeImage:
        assert stream is not None
        return fake_image

    def fake_image_to_string(image: FakeImage, lang: str, timeout: int) -> str:
        assert image is fake_image
        assert lang == "eng"
        assert timeout == 10
        return "  Synthetic certificate text\n"

    monkeypatch.setattr(ocr_provider.Image, "open", fake_open)
    monkeypatch.setattr(ocr_provider.pytesseract, "image_to_string", fake_image_to_string)

    result = TesseractOCRProvider().extract_text(b"validated-image-bytes")

    assert result == OCRResult(
        status=OCRStatus.SUCCESS,
        text="Synthetic certificate text",
    )


def test_tesseract_provider_returns_empty_outcome_for_blank_ocr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ocr_provider.Image, "open", lambda stream: FakeImage())
    monkeypatch.setattr(
        ocr_provider.pytesseract,
        "image_to_string",
        lambda image, lang, timeout: " \n\t ",
    )

    result = TesseractOCRProvider().extract_text(b"validated-image-bytes")

    assert result.status == OCRStatus.EMPTY
    assert result.text == ""
    assert result.message == "No readable text was found in this image."


def test_tesseract_provider_handles_missing_tesseract_as_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_missing_tesseract(image: FakeImage, lang: str, timeout: int) -> str:
        raise ocr_provider.pytesseract.TesseractNotFoundError()

    monkeypatch.setattr(ocr_provider.Image, "open", lambda stream: FakeImage())
    monkeypatch.setattr(
        ocr_provider.pytesseract,
        "image_to_string",
        raise_missing_tesseract,
    )

    result = TesseractOCRProvider().extract_text(b"validated-image-bytes")

    assert result == OCRResult(
        status=OCRStatus.UNAVAILABLE,
        message="OCR provider is unavailable.",
    )


def test_tesseract_provider_handles_timeout_as_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_timeout(image: FakeImage, lang: str, timeout: int) -> str:
        raise RuntimeError("Tesseract process timeout")

    monkeypatch.setattr(ocr_provider.Image, "open", lambda stream: FakeImage())
    monkeypatch.setattr(ocr_provider.pytesseract, "image_to_string", raise_timeout)

    result = TesseractOCRProvider().extract_text(b"validated-image-bytes")

    assert result == OCRResult(
        status=OCRStatus.UNAVAILABLE,
        message="OCR provider timed out.",
    )


def test_tesseract_provider_handles_provider_exception_safely(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_provider_error(image: FakeImage, lang: str, timeout: int) -> str:
        raise ValueError("internal provider details")

    monkeypatch.setattr(ocr_provider.Image, "open", lambda stream: FakeImage())
    monkeypatch.setattr(ocr_provider.pytesseract, "image_to_string", raise_provider_error)

    result = TesseractOCRProvider().extract_text(b"validated-image-bytes")

    assert result == OCRResult(
        status=OCRStatus.PROVIDER_ERROR,
        message="OCR provider could not process this image.",
    )


def test_tesseract_provider_handles_image_inspection_failure_safely(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_unidentified_image(stream: object) -> FakeImage:
        raise ocr_provider.UnidentifiedImageError("cannot identify image")

    monkeypatch.setattr(ocr_provider.Image, "open", raise_unidentified_image)

    result = TesseractOCRProvider().extract_text(b"invalid-image-bytes")

    assert result == OCRResult(
        status=OCRStatus.PROVIDER_ERROR,
        message="OCR provider could not inspect this image.",
    )


def test_tesseract_provider_keeps_configuration_inside_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen_config = {}

    def fake_image_to_string(image: FakeImage, lang: str, timeout: int) -> str:
        seen_config["language"] = lang
        seen_config["timeout_seconds"] = timeout
        return "Configured OCR text"

    monkeypatch.setattr(ocr_provider.Image, "open", lambda stream: FakeImage())
    monkeypatch.setattr(ocr_provider.pytesseract, "image_to_string", fake_image_to_string)

    result = TesseractOCRProvider(language="hin", timeout_seconds=3).extract_text(
        b"validated-image-bytes"
    )

    assert result.status == OCRStatus.SUCCESS
    assert seen_config == {"language": "hin", "timeout_seconds": 3}


def test_tesseract_provider_rejects_invalid_configuration() -> None:
    with pytest.raises(ValueError):
        TesseractOCRProvider(language=" ")

    with pytest.raises(ValueError):
        TesseractOCRProvider(timeout_seconds=0)
