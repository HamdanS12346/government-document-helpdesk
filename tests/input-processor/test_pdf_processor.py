"""PDF processor boundary tests with deterministic provider outcomes."""

from io import BytesIO

import pytest
from pypdf import PdfWriter
from pydantic import ValidationError

from app.input_processing.errors import InputProcessingErrorCode
from app.input_processing import pdf_processor
from app.input_processing.pdf_processor import (
    MAX_PDF_PAGE_COUNT,
    PDFClassificationResult,
    PDFDocumentType,
    PDFExtractionResult,
    PDFExtractionStatus,
    PDFExtractor,
    PDFPageText,
    PDFProcessingResult,
    PendingPDFExtractor,
    classify_pdf_content,
    classify_pdf_page_texts,
    get_pdf_page_count,
    process_pdf_attachment,
    validate_pdf_page_count,
)
from app.input_processing.schemas import (
    Attachment,
    AttachmentProcessingError,
    InputModality,
    ValidatedAttachment,
)
from guardrails.input_processor import MAX_PDF_PAGE_COUNT as GUARDRAIL_PDF_PAGE_LIMIT


def make_pdf_bytes(page_count: int) -> bytes:
    writer = PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=72, height=72)
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def make_validated_pdf(
    *,
    filename: str = "sample.pdf",
    page_count: int = 1,
) -> ValidatedAttachment:
    return ValidatedAttachment(
        attachment=Attachment(
            filename=filename,
            media_type="application/pdf",
            content=make_pdf_bytes(page_count),
        ),
        modality=InputModality.PDF,
    )


class CountingPDFExtractor:
    def __init__(self, result: PDFExtractionResult) -> None:
        self.result = result
        self.calls = 0

    def extract(self, pdf_content: bytes) -> PDFExtractionResult:
        self.calls += 1
        assert pdf_content
        return self.result


class RaisingPDFExtractor:
    def __init__(self) -> None:
        self.calls = 0

    def extract(self, pdf_content: bytes) -> PDFExtractionResult:
        self.calls += 1
        raise RuntimeError("provider internals should not leak")


class MalformedPDFExtractor:
    def __init__(self, result: object) -> None:
        self.result = result
        self.calls = 0

    def extract(self, pdf_content: bytes) -> object:
        self.calls += 1
        return self.result


class FakePDFPage:
    def __init__(self, text: str | None) -> None:
        self.text = text

    def extract_text(self) -> str | None:
        return self.text


class FakePDFReader:
    def __init__(self, stream: object) -> None:
        assert stream is not None
        self.pages = [
            FakePDFPage("Page one machine text"),
            FakePDFPage(None),
            FakePDFPage("  Page three machine text  "),
        ]


class RaisingPDFReader:
    def __init__(self, stream: object) -> None:
        raise RuntimeError("parser internals should not leak")


def test_pdf_extraction_result_accepts_text_based_success() -> None:
    result = PDFExtractionResult(
        status=PDFExtractionStatus.SUCCESS,
        document_type=PDFDocumentType.TEXT_BASED,
        pages=[PDFPageText(page_number=1, text="Synthetic government form text")],
    )

    assert result.status == PDFExtractionStatus.SUCCESS
    assert result.document_type == PDFDocumentType.TEXT_BASED
    assert result.pages[0].text == "Synthetic government form text"


@pytest.mark.parametrize(
    "document_type",
    [
        PDFDocumentType.TEXT_BASED,
        PDFDocumentType.SCANNED,
        PDFDocumentType.MIXED,
    ],
)
def test_pdf_extraction_result_supports_required_pdf_classifications(
    document_type: PDFDocumentType,
) -> None:
    result = PDFExtractionResult(
        status=PDFExtractionStatus.SUCCESS,
        document_type=document_type,
        pages=[
            PDFPageText(page_number=1, text="Page one text"),
            PDFPageText(page_number=2, text="Page two text"),
        ],
    )

    assert result.document_type == document_type
    assert [page.page_number for page in result.pages] == [1, 2]


@pytest.mark.parametrize(
    ("status", "message"),
    [
        (PDFExtractionStatus.EXTRACTION_FAILURE, "PDF text could not be extracted."),
        (PDFExtractionStatus.UNAVAILABLE, "PDF extraction provider is unavailable."),
        (PDFExtractionStatus.TIMEOUT, "PDF extraction provider timed out."),
        (PDFExtractionStatus.MALFORMED_RESPONSE, "PDF extraction provider returned an invalid result."),
        (PDFExtractionStatus.CORRUPT_PDF, "This PDF appears to be corrupt or unreadable."),
    ],
)
def test_pdf_extraction_result_accepts_controlled_failure_outcomes(
    status: PDFExtractionStatus,
    message: str,
) -> None:
    result = PDFExtractionResult(status=status, message=message)

    assert result.status == status
    assert result.document_type is None
    assert result.pages == []
    assert result.message == message


def test_successful_pdf_extraction_requires_document_type() -> None:
    with pytest.raises(ValidationError):
        PDFExtractionResult(
            status=PDFExtractionStatus.SUCCESS,
            pages=[PDFPageText(page_number=1, text="Page text")],
        )


def test_successful_pdf_extraction_requires_page_results() -> None:
    with pytest.raises(ValidationError):
        PDFExtractionResult(
            status=PDFExtractionStatus.SUCCESS,
            document_type=PDFDocumentType.TEXT_BASED,
        )


@pytest.mark.parametrize(
    "status",
    [
        PDFExtractionStatus.EXTRACTION_FAILURE,
        PDFExtractionStatus.UNAVAILABLE,
        PDFExtractionStatus.TIMEOUT,
        PDFExtractionStatus.MALFORMED_RESPONSE,
        PDFExtractionStatus.CORRUPT_PDF,
    ],
)
def test_failed_pdf_extraction_rejects_extracted_content(
    status: PDFExtractionStatus,
) -> None:
    with pytest.raises(ValidationError):
        PDFExtractionResult(
            status=status,
            document_type=PDFDocumentType.TEXT_BASED,
            pages=[PDFPageText(page_number=1, text="Untrusted failed-provider text")],
            message="PDF extraction failed.",
        )


@pytest.mark.parametrize(
    "status",
    [
        PDFExtractionStatus.EXTRACTION_FAILURE,
        PDFExtractionStatus.UNAVAILABLE,
        PDFExtractionStatus.TIMEOUT,
        PDFExtractionStatus.MALFORMED_RESPONSE,
        PDFExtractionStatus.CORRUPT_PDF,
    ],
)
def test_failed_pdf_extraction_requires_safe_message(
    status: PDFExtractionStatus,
) -> None:
    with pytest.raises(ValidationError):
        PDFExtractionResult(status=status)


def test_pdf_extraction_result_rejects_provider_specific_payloads() -> None:
    with pytest.raises(ValidationError):
        PDFExtractionResult.model_validate(
            {
                "status": "success",
                "document_type": "text_based",
                "pages": [{"page_number": 1, "text": "Page text"}],
                "docling_document": {"provider": "internal"},
            }
        )


def test_pdf_page_text_requires_positive_page_number() -> None:
    with pytest.raises(ValidationError):
        PDFPageText(page_number=0, text="Invalid page")


def test_mock_provider_can_satisfy_pdf_extractor_interface() -> None:
    class MockPDFExtractor:
        def extract(self, pdf_content: bytes) -> PDFExtractionResult:
            assert pdf_content == b"%PDF-1.4 synthetic bytes"
            return PDFExtractionResult(
                status=PDFExtractionStatus.SUCCESS,
                document_type=PDFDocumentType.MIXED,
                pages=[
                    PDFPageText(page_number=1, text="Text page"),
                    PDFPageText(page_number=2, text="OCR page"),
                ],
            )

    extractor: PDFExtractor = MockPDFExtractor()

    result = extractor.extract(b"%PDF-1.4 synthetic bytes")

    assert result.status == PDFExtractionStatus.SUCCESS
    assert result.document_type == PDFDocumentType.MIXED


def test_pending_pdf_extractor_keeps_provider_choice_internal() -> None:
    result = PendingPDFExtractor().extract(b"%PDF-1.4 synthetic bytes")

    assert result == PDFExtractionResult(
        status=PDFExtractionStatus.UNAVAILABLE,
        message="PDF extraction provider is not configured.",
    )


@pytest.mark.parametrize(
    ("pages", "expected_type"),
    [
        (
            [
                PDFPageText(page_number=1, text="Text page"),
                PDFPageText(page_number=2, text="Another text page"),
            ],
            PDFDocumentType.TEXT_BASED,
        ),
        (
            [
                PDFPageText(page_number=1, text=""),
                PDFPageText(page_number=2, text="   "),
            ],
            PDFDocumentType.SCANNED,
        ),
        (
            [
                PDFPageText(page_number=1, text="Text page"),
                PDFPageText(page_number=2, text=""),
            ],
            PDFDocumentType.MIXED,
        ),
    ],
)
def test_classify_pdf_page_texts_identifies_pdf_type(
    pages: list[PDFPageText],
    expected_type: PDFDocumentType,
) -> None:
    assert classify_pdf_page_texts(pages) == expected_type


def test_classify_pdf_page_texts_rejects_missing_page_data() -> None:
    with pytest.raises(Exception) as exc_info:
        classify_pdf_page_texts([])

    assert exc_info.value.code == InputProcessingErrorCode.UNREADABLE_CONTENT
    assert exc_info.value.message == "This PDF could not be inspected for classification."


def test_classify_pdf_content_inspects_page_text_without_provider_payloads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(pdf_processor, "PdfReader", FakePDFReader)

    result = classify_pdf_content(b"%PDF-1.4 synthetic bytes")

    assert result == PDFClassificationResult(
        document_type=PDFDocumentType.MIXED,
        pages=[
            PDFPageText(page_number=1, text="Page one machine text"),
            PDFPageText(page_number=2, text=""),
            PDFPageText(page_number=3, text="Page three machine text"),
        ],
    )
    assert not hasattr(result, "pdf_reader")
    assert not hasattr(result, "docling_document")


def test_classify_pdf_content_returns_controlled_failure_for_unreadable_pdf(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(pdf_processor, "PdfReader", RaisingPDFReader)

    with pytest.raises(Exception) as exc_info:
        classify_pdf_content(b"%PDF-1.4 corrupt bytes")

    assert exc_info.value.code == InputProcessingErrorCode.UNREADABLE_CONTENT
    assert exc_info.value.message == "This PDF could not be inspected for classification."


def test_pdf_page_count_uses_transient_bytes() -> None:
    assert get_pdf_page_count(make_pdf_bytes(3)) == 3


def test_pdf_page_limit_value_matches_guardrail_boundary() -> None:
    assert MAX_PDF_PAGE_COUNT == 10
    assert GUARDRAIL_PDF_PAGE_LIMIT == MAX_PDF_PAGE_COUNT


def test_pdf_page_count_validation_accepts_configured_limit() -> None:
    validate_pdf_page_count(
        make_pdf_bytes(MAX_PDF_PAGE_COUNT),
        max_page_count=MAX_PDF_PAGE_COUNT,
    )


def test_pdf_page_count_validation_rejects_over_configured_limit() -> None:
    with pytest.raises(Exception) as exc_info:
        validate_pdf_page_count(
            make_pdf_bytes(MAX_PDF_PAGE_COUNT + 1),
            max_page_count=MAX_PDF_PAGE_COUNT,
        )

    assert exc_info.value.code == InputProcessingErrorCode.PDF_PAGE_LIMIT_EXCEEDED
    assert exc_info.value.message == (
        f"This PDF has too many pages. Upload a PDF with {MAX_PDF_PAGE_COUNT} pages or fewer."
    )


def test_pdf_page_count_validation_wraps_unreadable_pdf_safely() -> None:
    with pytest.raises(Exception) as exc_info:
        validate_pdf_page_count(b"%PDF-1.4\nnot readable\n%%EOF")

    assert exc_info.value.code == InputProcessingErrorCode.UNREADABLE_CONTENT
    assert exc_info.value.message == "This PDF could not be read for validation."


def test_process_pdf_attachment_validates_page_count_before_extraction() -> None:
    extractor = CountingPDFExtractor(
        PDFExtractionResult(
            status=PDFExtractionStatus.SUCCESS,
            document_type=PDFDocumentType.TEXT_BASED,
            pages=[PDFPageText(page_number=1, text="unused")],
        )
    )

    result = process_pdf_attachment(
        make_validated_pdf(page_count=MAX_PDF_PAGE_COUNT + 1),
        extractor,
    )

    assert extractor.calls == 0
    assert result.extraction_result is None
    assert result.error is not None
    assert result.error.code == InputProcessingErrorCode.PDF_PAGE_LIMIT_EXCEEDED


def test_process_pdf_attachment_calls_extractor_after_page_count_validation() -> None:
    extractor = CountingPDFExtractor(
        PDFExtractionResult(
            status=PDFExtractionStatus.SUCCESS,
            document_type=PDFDocumentType.TEXT_BASED,
            pages=[PDFPageText(page_number=1, text="Synthetic PDF text")],
        )
    )

    result = process_pdf_attachment(make_validated_pdf(), extractor)

    assert extractor.calls == 1
    assert result.error is None
    assert result.extraction_result == extractor.result


def test_process_pdf_attachment_classifies_pdf_before_extraction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = []

    def fake_validate_pdf_page_count(pdf_content: bytes, *, max_page_count: int) -> None:
        events.append("validate")

    def fake_classify_pdf_content(pdf_content: bytes) -> PDFClassificationResult:
        events.append("classify")
        return PDFClassificationResult(
            document_type=PDFDocumentType.TEXT_BASED,
            pages=[PDFPageText(page_number=1, text="Machine text")],
        )

    class EventPDFExtractor:
        def extract(self, pdf_content: bytes) -> PDFExtractionResult:
            events.append("extract")
            return PDFExtractionResult(
                status=PDFExtractionStatus.SUCCESS,
                document_type=PDFDocumentType.TEXT_BASED,
                pages=[PDFPageText(page_number=1, text="Machine text")],
            )

    monkeypatch.setattr(
        pdf_processor,
        "validate_pdf_page_count",
        fake_validate_pdf_page_count,
    )
    monkeypatch.setattr(pdf_processor, "classify_pdf_content", fake_classify_pdf_content)

    result = process_pdf_attachment(make_validated_pdf(), EventPDFExtractor())

    assert result.error is None
    assert events == ["validate", "classify", "extract"]


def test_process_pdf_attachment_rejects_unclassifiable_pdf_before_extraction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    extractor = CountingPDFExtractor(
        PDFExtractionResult(
            status=PDFExtractionStatus.SUCCESS,
            document_type=PDFDocumentType.TEXT_BASED,
            pages=[PDFPageText(page_number=1, text="unused")],
        )
    )

    def fake_classify_pdf_content(pdf_content: bytes) -> PDFClassificationResult:
        raise pdf_processor.InputProcessingError(
            InputProcessingErrorCode.UNREADABLE_CONTENT,
            "This PDF could not be inspected for classification.",
        )

    monkeypatch.setattr(pdf_processor, "classify_pdf_content", fake_classify_pdf_content)

    result = process_pdf_attachment(make_validated_pdf(), extractor)

    assert extractor.calls == 0
    assert result.extraction_result is None
    assert result.error is not None
    assert result.error.code == InputProcessingErrorCode.UNREADABLE_CONTENT
    assert result.error.message == "This PDF could not be inspected for classification."


def test_process_pdf_attachment_honors_custom_page_limit() -> None:
    extractor = CountingPDFExtractor(
        PDFExtractionResult(
            status=PDFExtractionStatus.SUCCESS,
            document_type=PDFDocumentType.TEXT_BASED,
            pages=[PDFPageText(page_number=1, text="unused")],
        )
    )

    result = process_pdf_attachment(
        make_validated_pdf(page_count=6),
        extractor,
        max_page_count=5,
    )

    assert extractor.calls == 0
    assert result.error is not None
    assert result.error.code == InputProcessingErrorCode.PDF_PAGE_LIMIT_EXCEEDED
    assert "5 pages or fewer" in result.error.message


def test_process_pdf_attachment_rejects_non_pdf_without_extraction() -> None:
    extractor = CountingPDFExtractor(
        PDFExtractionResult(
            status=PDFExtractionStatus.SUCCESS,
            document_type=PDFDocumentType.TEXT_BASED,
            pages=[PDFPageText(page_number=1, text="unused")],
        )
    )
    validated = ValidatedAttachment(
        attachment=Attachment(
            filename="sample.png",
            media_type="image/png",
            content=b"\x89PNG\r\n\x1a\nsynthetic bytes",
        ),
        modality=InputModality.PNG,
    )

    result = process_pdf_attachment(validated, extractor)

    assert extractor.calls == 0
    assert result.error is not None
    assert result.error.code == InputProcessingErrorCode.UNSUPPORTED_FORMAT


def test_process_pdf_attachment_returns_controlled_failure_for_provider_exception() -> None:
    extractor = RaisingPDFExtractor()

    result = process_pdf_attachment(make_validated_pdf(), extractor)

    assert extractor.calls == 1
    assert result.extraction_result is None
    assert result.error is not None
    assert result.error.code == InputProcessingErrorCode.EXTRACTION_FAILURE
    assert result.error.message == "PDF extraction could not be completed."


@pytest.mark.parametrize("malformed_result", [None, {"status": "success"}, object()])
def test_process_pdf_attachment_returns_controlled_failure_for_malformed_provider_response(
    malformed_result: object,
) -> None:
    extractor = MalformedPDFExtractor(malformed_result)

    result = process_pdf_attachment(make_validated_pdf(), extractor)

    assert extractor.calls == 1
    assert result.extraction_result is None
    assert result.error is not None
    assert result.error.code == InputProcessingErrorCode.EXTRACTION_FAILURE
    assert result.error.message == "PDF extraction provider returned an invalid result."


def test_pdf_processing_result_requires_extraction_result_or_error() -> None:
    with pytest.raises(ValidationError):
        PDFProcessingResult()

    with pytest.raises(ValidationError):
        PDFProcessingResult(
            extraction_result=PDFExtractionResult(
                status=PDFExtractionStatus.UNAVAILABLE,
                message="PDF extraction provider is unavailable.",
            ),
            error=AttachmentProcessingError(
                filename="sample.pdf",
                code=InputProcessingErrorCode.EXTRACTION_FAILURE,
                message="PDF extraction failed.",
            ),
        )
