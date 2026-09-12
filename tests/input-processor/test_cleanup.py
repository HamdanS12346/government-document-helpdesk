"""Cleanup lifecycle tests for the Input Processor."""

from io import BytesIO
from pathlib import Path

import pytest
from pypdf import PdfWriter

from app.input_processing import image_processor
from app.input_processing import pdf_processor
from app.input_processing import processors
from app.input_processing.errors import InputProcessingError, InputProcessingErrorCode
from app.input_processing.image_processor import ImageProcessingResult
from app.input_processing.ocr_provider import OCRResult, OCRStatus
from app.input_processing.pdf_processor import PDFProcessingResult
from app.input_processing.schemas import Attachment, InputModality, InputRequest, ValidatedAttachment
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


class TrackedBytesIO:
    events: list[str] = []

    def __init__(self, content: bytes) -> None:
        self.content = content
        self.closed = False

    def __enter__(self) -> "TrackedBytesIO":
        self.events.append("enter")
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def close(self) -> None:
        self.closed = True
        self.events.append("close")


class FakePDFReader:
    def __init__(self, stream: TrackedBytesIO) -> None:
        self.stream = stream
        self.pages = [FakePDFPage("Synthetic PDF text")]


class RaisingPDFReader:
    def __init__(self, stream: TrackedBytesIO) -> None:
        raise RuntimeError("parser failed")


class FakePDFPage:
    def __init__(self, text: str) -> None:
        self.text = text

    def extract_text(self) -> str:
        return self.text


def make_validated_image() -> ValidatedAttachment:
    return ValidatedAttachment(
        attachment=Attachment(
            filename="fictional_form.png",
            media_type="image/png",
            content=VALID_IMAGE.read_bytes(),
        ),
        modality=InputModality.PNG,
    )


def make_pdf_bytes() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


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


def test_pdf_page_count_stream_is_closed_after_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    TrackedBytesIO.events = []
    monkeypatch.setattr(pdf_processor, "BytesIO", TrackedBytesIO)
    monkeypatch.setattr(pdf_processor, "PdfReader", FakePDFReader)

    assert pdf_processor.get_pdf_page_count(b"%PDF-1.4 synthetic bytes") == 1
    assert TrackedBytesIO.events == ["enter", "close"]


def test_pdf_page_count_stream_is_closed_after_validation_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    TrackedBytesIO.events = []
    monkeypatch.setattr(pdf_processor, "BytesIO", TrackedBytesIO)
    monkeypatch.setattr(pdf_processor, "PdfReader", RaisingPDFReader)

    with pytest.raises(InputProcessingError):
        pdf_processor.get_pdf_page_count(b"%PDF-1.4 corrupt bytes")

    assert TrackedBytesIO.events == ["enter", "close"]


def test_pdf_classification_stream_is_closed_after_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    TrackedBytesIO.events = []
    monkeypatch.setattr(pdf_processor, "BytesIO", TrackedBytesIO)
    monkeypatch.setattr(pdf_processor, "PdfReader", FakePDFReader)

    result = pdf_processor.classify_pdf_content(b"%PDF-1.4 synthetic bytes")

    assert result.document_type == pdf_processor.PDFDocumentType.TEXT_BASED
    assert TrackedBytesIO.events == ["enter", "close"]


def test_pdf_classification_stream_is_closed_after_parser_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    TrackedBytesIO.events = []
    monkeypatch.setattr(pdf_processor, "BytesIO", TrackedBytesIO)
    monkeypatch.setattr(pdf_processor, "PdfReader", RaisingPDFReader)

    with pytest.raises(InputProcessingError):
        pdf_processor.classify_pdf_content(b"%PDF-1.4 corrupt bytes")

    assert TrackedBytesIO.events == ["enter", "close"]


def test_public_processor_creates_no_temp_files_after_success(tmp_path) -> None:
    before = set(tmp_path.iterdir())

    result = processors.process_input(InputRequest(user_query="Text-only success."))

    assert result.success is True
    assert set(tmp_path.iterdir()) == before


def test_public_processor_creates_no_temp_files_after_validation_failure(tmp_path) -> None:
    before = set(tmp_path.iterdir())

    result = processors.process_input(
        InputRequest(
            attachments=[
                Attachment(
                    filename="bad.pdf",
                    media_type="application/pdf",
                    content=b"not a pdf",
                )
            ],
        )
    )

    assert result.success is False
    assert set(tmp_path.iterdir()) == before


def test_public_processor_creates_no_temp_files_after_ocr_failure(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before = set(tmp_path.iterdir())

    def fake_process_image_attachment(validated_attachment, ocr_provider):
        return ImageProcessingResult(
            error=processors.AttachmentProcessingError(
                filename=validated_attachment.attachment.filename,
                code=InputProcessingErrorCode.OCR_FAILURE,
                message="OCR could not be completed for this image.",
            )
        )

    monkeypatch.setattr(processors, "process_image_attachment", fake_process_image_attachment)

    result = processors.process_input(
        InputRequest(
            attachments=[
                Attachment(
                    filename="sample.png",
                    media_type="image/png",
                    content=b"\x89PNG\r\n\x1a\nsynthetic bytes",
                )
            ],
        ),
        ocr_provider=StaticOCRProvider(OCRResult(status=OCRStatus.SUCCESS, text="unused")),
    )

    assert result.success is False
    assert set(tmp_path.iterdir()) == before


def test_public_processor_creates_no_temp_files_after_pdf_extraction_failure(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before = set(tmp_path.iterdir())

    def fake_process_pdf_attachment(
        validated_attachment,
        pdf_extractor,
        *,
        ocr_provider=None,
        page_image_extractor=None,
    ):
        return PDFProcessingResult(
            error=processors.AttachmentProcessingError(
                filename=validated_attachment.attachment.filename,
                code=InputProcessingErrorCode.EXTRACTION_FAILURE,
                message="PDF content could not be processed safely.",
            )
        )

    monkeypatch.setattr(processors, "process_pdf_attachment", fake_process_pdf_attachment)

    result = processors.process_input(
        InputRequest(
            attachments=[
                Attachment(
                    filename="sample.pdf",
                    media_type="application/pdf",
                    content=make_pdf_bytes(),
                )
            ],
        )
    )

    assert result.success is False
    assert set(tmp_path.iterdir()) == before


def test_public_processor_creates_no_temp_files_after_pii_processing_failure(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before = set(tmp_path.iterdir())

    def fake_process_image_attachment(validated_attachment, ocr_provider):
        return ImageProcessingResult(
            error=processors.AttachmentProcessingError(
                filename=validated_attachment.attachment.filename,
                code=InputProcessingErrorCode.PII_PROCESSING_FAILURE,
                message="PII processing could not be completed safely.",
            )
        )

    monkeypatch.setattr(processors, "process_image_attachment", fake_process_image_attachment)

    result = processors.process_input(
        InputRequest(
            attachments=[
                Attachment(
                    filename="sample.png",
                    media_type="image/png",
                    content=b"\x89PNG\r\n\x1a\nsynthetic bytes",
                )
            ],
        ),
        ocr_provider=StaticOCRProvider(OCRResult(status=OCRStatus.SUCCESS, text="unused")),
    )

    assert result.success is False
    assert set(tmp_path.iterdir()) == before


def test_public_processor_creates_no_temp_files_after_unexpected_exception(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before = set(tmp_path.iterdir())

    def raise_unexpected(validated_attachment, ocr_provider):
        raise RuntimeError("internal path should not leak")

    monkeypatch.setattr(processors, "process_image_attachment", raise_unexpected)

    result = processors.process_input(
        InputRequest(
            attachments=[
                Attachment(
                    filename="sample.png",
                    media_type="image/png",
                    content=b"\x89PNG\r\n\x1a\nsynthetic bytes",
                )
            ],
        ),
        ocr_provider=StaticOCRProvider(OCRResult(status=OCRStatus.SUCCESS, text="unused")),
    )

    assert result.success is False
    assert set(tmp_path.iterdir()) == before
