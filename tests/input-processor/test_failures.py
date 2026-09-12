"""Failure-injection tests for Input Processor PDF handling."""

from io import BytesIO

import pytest
from pypdf import PdfWriter

from app.input_processing import pdf_processor
from app.input_processing.errors import InputProcessingErrorCode
from app.input_processing.ocr_provider import OCRResult, OCRStatus
from app.input_processing.pdf_processor import (
    PDFClassificationResult,
    PDFDocumentType,
    PDFExtractionResult,
    PDFExtractionStatus,
    PDFPageImage,
    PDFPageText,
    PendingPDFExtractor,
    process_pdf_attachment,
)
from app.input_processing.schemas import Attachment, InputModality, ValidatedAttachment


def make_pdf_bytes(page_count: int = 1) -> bytes:
    writer = PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=72, height=72)
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def make_validated_pdf(
    content: bytes | None = None,
    *,
    page_count: int = 1,
) -> ValidatedAttachment:
    return ValidatedAttachment(
        attachment=Attachment(
            filename="sample.pdf",
            media_type="application/pdf",
            content=content or make_pdf_bytes(page_count),
        ),
        modality=InputModality.PDF,
    )


class StaticOCRProvider:
    def __init__(self, results: list[OCRResult]) -> None:
        self.results = results
        self.calls = 0

    def extract_text(self, image_content: bytes) -> OCRResult:
        self.calls += 1
        return self.results[self.calls - 1]


class StaticPDFPageImageExtractor:
    def __init__(self, page_images: list[PDFPageImage]) -> None:
        self.page_images = page_images
        self.calls = 0

    def extract_page_images(self, pdf_content: bytes) -> list[PDFPageImage]:
        self.calls += 1
        return self.page_images


class ControlledFailurePDFPageImageExtractor:
    def __init__(self, message: str) -> None:
        self.message = message
        self.calls = 0

    def extract_page_images(self, pdf_content: bytes) -> list[PDFPageImage]:
        self.calls += 1
        raise pdf_processor.InputProcessingError(
            InputProcessingErrorCode.EXTRACTION_FAILURE,
            self.message,
        )


class MalformedPDFPageImageExtractor:
    def __init__(self, result: object) -> None:
        self.result = result
        self.calls = 0

    def extract_page_images(self, pdf_content: bytes) -> object:
        self.calls += 1
        return self.result


class RaisingPDFReader:
    def __init__(self, stream: object) -> None:
        raise RuntimeError("parser internals should not leak")


def test_mock_provider_text_pdf_extraction_succeeds_without_ocr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_classify_pdf_content(pdf_content: bytes) -> PDFClassificationResult:
        return PDFClassificationResult(
            document_type=PDFDocumentType.TEXT_BASED,
            pages=[PDFPageText(page_number=1, text="Text PDF content")],
        )

    monkeypatch.setattr(pdf_processor, "classify_pdf_content", fake_classify_pdf_content)

    result = process_pdf_attachment(make_validated_pdf(), PendingPDFExtractor())

    assert result.error is None
    assert result.pdf_content is not None
    assert result.pdf_content.extracted_text == "Text PDF content"


def test_mock_provider_scanned_pdf_ocr_path_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_classify_pdf_content(pdf_content: bytes) -> PDFClassificationResult:
        return PDFClassificationResult(
            document_type=PDFDocumentType.SCANNED,
            pages=[PDFPageText(page_number=1, text="")],
        )

    page_image_extractor = StaticPDFPageImageExtractor(
        [PDFPageImage(page_number=1, image_content=b"page-one-image")]
    )
    ocr_provider = StaticOCRProvider(
        [OCRResult(status=OCRStatus.SUCCESS, text="Scanned PDF content")]
    )
    monkeypatch.setattr(pdf_processor, "classify_pdf_content", fake_classify_pdf_content)

    result = process_pdf_attachment(
        make_validated_pdf(),
        PendingPDFExtractor(),
        ocr_provider=ocr_provider,
        page_image_extractor=page_image_extractor,
    )

    assert result.error is None
    assert result.pdf_content is not None
    assert result.pdf_content.extracted_text == "Scanned PDF content"


def test_mock_provider_mixed_pdf_text_plus_ocr_path_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_classify_pdf_content(pdf_content: bytes) -> PDFClassificationResult:
        return PDFClassificationResult(
            document_type=PDFDocumentType.MIXED,
            pages=[
                PDFPageText(page_number=1, text="Machine text"),
                PDFPageText(page_number=2, text=""),
            ],
        )

    page_image_extractor = StaticPDFPageImageExtractor(
        [PDFPageImage(page_number=2, image_content=b"page-two-image")]
    )
    ocr_provider = StaticOCRProvider(
        [OCRResult(status=OCRStatus.SUCCESS, text="OCR text")]
    )
    monkeypatch.setattr(pdf_processor, "classify_pdf_content", fake_classify_pdf_content)

    result = process_pdf_attachment(
        make_validated_pdf(page_count=2),
        PendingPDFExtractor(),
        ocr_provider=ocr_provider,
        page_image_extractor=page_image_extractor,
    )

    assert result.error is None
    assert result.pdf_content is not None
    assert result.pdf_content.extracted_text == "Machine text\nOCR text"


@pytest.mark.parametrize(
    "message",
    [
        "PDF page image provider is unavailable.",
        "PDF page image provider timed out.",
    ],
)
def test_mock_provider_unavailable_and_timeout_are_controlled(
    message: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_classify_pdf_content(pdf_content: bytes) -> PDFClassificationResult:
        return PDFClassificationResult(
            document_type=PDFDocumentType.SCANNED,
            pages=[PDFPageText(page_number=1, text="")],
        )

    page_image_extractor = ControlledFailurePDFPageImageExtractor(message)
    monkeypatch.setattr(pdf_processor, "classify_pdf_content", fake_classify_pdf_content)

    result = process_pdf_attachment(
        make_validated_pdf(),
        PendingPDFExtractor(),
        ocr_provider=StaticOCRProvider([]),
        page_image_extractor=page_image_extractor,
    )

    assert page_image_extractor.calls == 1
    assert result.pdf_content is None
    assert result.error is not None
    assert result.error.code == InputProcessingErrorCode.EXTRACTION_FAILURE
    assert result.error.message == message


@pytest.mark.parametrize(
    "malformed_result",
    [
        None,
        {"page_number": 1, "image_content": b"page-one-image"},
        [object()],
    ],
)
def test_mock_provider_malformed_response_is_controlled(
    malformed_result: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_classify_pdf_content(pdf_content: bytes) -> PDFClassificationResult:
        return PDFClassificationResult(
            document_type=PDFDocumentType.SCANNED,
            pages=[PDFPageText(page_number=1, text="")],
        )

    page_image_extractor = MalformedPDFPageImageExtractor(malformed_result)
    monkeypatch.setattr(pdf_processor, "classify_pdf_content", fake_classify_pdf_content)

    result = process_pdf_attachment(
        make_validated_pdf(),
        PendingPDFExtractor(),
        ocr_provider=StaticOCRProvider([]),
        page_image_extractor=page_image_extractor,
    )

    assert page_image_extractor.calls == 1
    assert result.pdf_content is None
    assert result.error is not None
    assert result.error.code == InputProcessingErrorCode.EXTRACTION_FAILURE
    assert result.error.message == "PDF page image extractor returned an invalid result."


def test_mock_provider_exception_is_controlled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class RaisingPDFPageImageExtractor:
        def extract_page_images(self, pdf_content: bytes) -> list[PDFPageImage]:
            raise RuntimeError("provider internals should not leak")

    def fake_classify_pdf_content(pdf_content: bytes) -> PDFClassificationResult:
        return PDFClassificationResult(
            document_type=PDFDocumentType.SCANNED,
            pages=[PDFPageText(page_number=1, text="")],
        )

    monkeypatch.setattr(pdf_processor, "classify_pdf_content", fake_classify_pdf_content)

    result = process_pdf_attachment(
        make_validated_pdf(),
        PendingPDFExtractor(),
        ocr_provider=StaticOCRProvider([]),
        page_image_extractor=RaisingPDFPageImageExtractor(),
    )

    assert result.pdf_content is None
    assert result.error is not None
    assert result.error.code == InputProcessingErrorCode.EXTRACTION_FAILURE
    assert result.error.message == "PDF page images could not be extracted."


def test_corrupt_invalid_pdf_returns_controlled_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(pdf_processor, "PdfReader", RaisingPDFReader)

    result = process_pdf_attachment(
        make_validated_pdf(b"%PDF-1.4\nnot readable\n%%EOF"),
        PendingPDFExtractor(),
    )

    assert result.pdf_content is None
    assert result.error is not None
    assert result.error.code == InputProcessingErrorCode.UNREADABLE_CONTENT
    assert result.error.message == "This PDF could not be read for validation."
