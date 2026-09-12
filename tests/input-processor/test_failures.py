"""Failure-injection tests for Input Processor PDF handling."""

from io import BytesIO

import pytest
from pypdf import PdfWriter

from app.input_processing import pdf_processor
from app.input_processing import processors
from app.input_processing.errors import InputProcessingErrorCode
from app.input_processing.image_processor import ImageProcessingResult
from app.input_processing.ocr_provider import OCRResult, OCRStatus
from app.input_processing.pdf_processor import (
    PDFClassificationResult,
    PDFDocumentType,
    PDFExtractionResult,
    PDFExtractionStatus,
    PDFPageImage,
    PDFPageText,
    PDFProcessingResult,
    PendingPDFExtractor,
    process_pdf_attachment,
)
from app.input_processing.schemas import (
    Attachment,
    AttachmentProcessingError,
    InputModality,
    InputRequest,
    ValidatedAttachment,
)


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


def test_public_processor_handles_ocr_unavailable_as_complete_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_process_image_attachment(validated_attachment, ocr_provider):
        return ImageProcessingResult(
            error=AttachmentProcessingError(
                filename=validated_attachment.attachment.filename,
                code=InputProcessingErrorCode.OCR_FAILURE,
                message="OCR provider is unavailable.",
            )
        )

    monkeypatch.setattr(processors, "process_image_attachment", fake_process_image_attachment)

    result = processors.process_input(
        InputRequest(
            attachments=[
                Attachment(
                    filename="image.png",
                    media_type="image/png",
                    content=b"\x89PNG\r\n\x1a\nsynthetic bytes",
                )
            ]
        ),
        ocr_provider=StaticOCRProvider([]),
    )

    assert result.success is False
    assert result.normalized_input is None
    assert result.attachment_statuses[0].error is not None
    assert result.attachment_statuses[0].error.code == InputProcessingErrorCode.OCR_FAILURE
    assert "unavailable" in result.attachment_statuses[0].error.message


@pytest.mark.parametrize(
    ("message", "expected_fragment"),
    [
        ("OCR provider timed out.", "timed out"),
        ("OCR provider could not process this image.", "could not process"),
    ],
)
def test_public_processor_handles_ocr_timeout_and_provider_error_with_text_success(
    message: str,
    expected_fragment: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_process_image_attachment(validated_attachment, ocr_provider):
        return ImageProcessingResult(
            error=AttachmentProcessingError(
                filename=validated_attachment.attachment.filename,
                code=InputProcessingErrorCode.OCR_FAILURE,
                message=message,
            )
        )

    monkeypatch.setattr(processors, "process_image_attachment", fake_process_image_attachment)

    result = processors.process_input(
        InputRequest(
            user_query="Text survives failed OCR.",
            attachments=[
                Attachment(
                    filename="image.png",
                    media_type="image/png",
                    content=b"\x89PNG\r\n\x1a\nsynthetic bytes",
                )
            ],
        ),
        ocr_provider=StaticOCRProvider([]),
    )

    assert result.success is True
    assert result.normalized_input is not None
    assert result.normalized_input.combined_text == "Text survives failed OCR."
    assert result.attachment_statuses[0].error is not None
    assert expected_fragment in result.attachment_statuses[0].error.message


def test_public_processor_wraps_ocr_exception_without_leaking_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_ocr_exception(validated_attachment, ocr_provider):
        raise RuntimeError("tesseract path C:\\private\\document.png")

    monkeypatch.setattr(processors, "process_image_attachment", raise_ocr_exception)

    result = processors.process_input(
        InputRequest(
            attachments=[
                Attachment(
                    filename="image.png",
                    media_type="image/png",
                    content=b"\x89PNG\r\n\x1a\nsynthetic bytes",
                )
            ]
        ),
        ocr_provider=StaticOCRProvider([]),
    )

    assert result.success is False
    assert result.attachment_statuses[0].error is not None
    assert (
        result.attachment_statuses[0].error.code
        == InputProcessingErrorCode.INTERNAL_PROCESSING_ERROR
    )
    assert result.attachment_statuses[0].error.message == (
        "This attachment could not be processed safely."
    )
    assert "C:\\private" not in str(result.model_dump(mode="json"))


def test_public_processor_handles_malformed_ocr_response_as_controlled_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def malformed_ocr_result(validated_attachment, ocr_provider):
        return ImageProcessingResult(
            error=AttachmentProcessingError(
                filename=validated_attachment.attachment.filename,
                code=InputProcessingErrorCode.OCR_FAILURE,
                message="OCR provider returned an invalid result.",
            )
        )

    monkeypatch.setattr(processors, "process_image_attachment", malformed_ocr_result)

    result = processors.process_input(
        InputRequest(
            attachments=[
                Attachment(
                    filename="image.png",
                    media_type="image/png",
                    content=b"\x89PNG\r\n\x1a\nsynthetic bytes",
                )
            ]
        ),
        ocr_provider=StaticOCRProvider([]),
    )

    assert result.success is False
    assert result.attachment_statuses[0].error is not None
    assert result.attachment_statuses[0].error.code == InputProcessingErrorCode.OCR_FAILURE
    assert "invalid result" in result.attachment_statuses[0].error.message


@pytest.mark.parametrize(
    ("message", "expected_code"),
    [
        ("PDF provider is unavailable.", InputProcessingErrorCode.EXTRACTION_FAILURE),
        ("PDF provider timed out.", InputProcessingErrorCode.EXTRACTION_FAILURE),
        ("PDF provider returned an invalid result.", InputProcessingErrorCode.EXTRACTION_FAILURE),
    ],
)
def test_public_processor_handles_pdf_provider_failures_as_partial_success(
    message: str,
    expected_code: InputProcessingErrorCode,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_process_pdf_attachment(
        validated_attachment,
        pdf_extractor,
        *,
        ocr_provider=None,
        page_image_extractor=None,
    ):
        return PDFProcessingResult(
            error=AttachmentProcessingError(
                filename=validated_attachment.attachment.filename,
                code=expected_code,
                message=message,
            )
        )

    monkeypatch.setattr(processors, "process_pdf_attachment", fake_process_pdf_attachment)

    result = processors.process_input(
        InputRequest(
            user_query="Text survives failed PDF.",
            attachments=[make_attachment_pdf()],
        )
    )

    assert result.success is True
    assert result.normalized_input is not None
    assert result.normalized_input.combined_text == "Text survives failed PDF."
    assert result.attachment_statuses[0].error is not None
    assert result.attachment_statuses[0].error.code == expected_code
    assert result.attachment_statuses[0].error.message == message


def test_public_processor_wraps_pdf_exception_without_leaking_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_pdf_exception(
        validated_attachment,
        pdf_extractor,
        *,
        ocr_provider=None,
        page_image_extractor=None,
    ):
        raise RuntimeError("docling failed at C:\\private\\sample.pdf")

    monkeypatch.setattr(processors, "process_pdf_attachment", raise_pdf_exception)

    result = processors.process_input(InputRequest(attachments=[make_attachment_pdf()]))

    assert result.success is False
    assert result.attachment_statuses[0].error is not None
    assert (
        result.attachment_statuses[0].error.code
        == InputProcessingErrorCode.INTERNAL_PROCESSING_ERROR
    )
    assert "docling" not in result.attachment_statuses[0].error.message.lower()
    assert "C:\\private" not in str(result.model_dump(mode="json"))


def test_public_processor_handles_pii_detector_failure_without_fabricated_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_process_image_attachment(validated_attachment, ocr_provider):
        return ImageProcessingResult(
            error=AttachmentProcessingError(
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
                    filename="image.png",
                    media_type="image/png",
                    content=b"\x89PNG\r\n\x1a\nABCDE1234F",
                )
            ]
        ),
        ocr_provider=StaticOCRProvider([]),
    )

    assert result.success is False
    assert result.normalized_input is None
    assert result.attachment_statuses[0].error is not None
    assert (
        result.attachment_statuses[0].error.code
        == InputProcessingErrorCode.PII_PROCESSING_FAILURE
    )
    assert "ABCDE1234F" not in str(result.model_dump(mode="json"))


@pytest.mark.parametrize(
    ("attachment", "expected_code"),
    [
        (
            Attachment(
                filename="bad.png",
                media_type="image/png",
                content=b"not a png",
            ),
            InputProcessingErrorCode.SIGNATURE_MISMATCH,
        ),
        (
            Attachment(
                filename="bad.pdf",
                media_type="application/pdf",
                content=b"not a pdf",
            ),
            InputProcessingErrorCode.SIGNATURE_MISMATCH,
        ),
        (
            Attachment(
                filename="bad.gif",
                media_type="image/gif",
                content=b"GIF89a",
            ),
            InputProcessingErrorCode.UNSUPPORTED_FORMAT,
        ),
    ],
)
def test_public_processor_handles_invalid_corrupt_and_unreadable_files(
    attachment: Attachment,
    expected_code: InputProcessingErrorCode,
) -> None:
    result = processors.process_input(InputRequest(attachments=[attachment]))

    assert result.success is False
    assert result.normalized_input is None
    assert result.attachment_statuses[0].error is not None
    assert result.attachment_statuses[0].error.code == expected_code
    assert "not a" not in result.attachment_statuses[0].error.message


def make_attachment_pdf() -> Attachment:
    return Attachment(
        filename="sample.pdf",
        media_type="application/pdf",
        content=make_pdf_bytes(),
    )
