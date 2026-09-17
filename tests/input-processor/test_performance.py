"""Performance measurement tests for the Input Processor.

These tests record stage timings without enforcing modality-specific thresholds.
"""

from io import BytesIO
from pathlib import Path
from time import perf_counter

import pytest
from pypdf import PdfWriter

from app.contracts.normalized_input import ImageContent, PDFContent
from app.input_processing import processors
from app.input_processing.image_processor import ImageProcessingResult
from app.input_processing.ocr_provider import OCRResult, OCRStatus
from app.input_processing.pdf_processor import (
    PDFClassificationResult,
    PDFDocumentType,
    PDFPageText,
    PDFProcessingResult,
    classify_pdf_content,
)
from app.input_processing.schemas import Attachment, InputRequest
from guardrails.input_processor import mask_pii_in_text, validate_attachment_modality
from app.input_processing.excel_processor import (
    OpenPyXLSpreadsheetParser,
    SpreadsheetInspectionStatus,
    build_spreadsheet_content,
    build_spreadsheet_preview,
    build_spreadsheet_text_projection,
)
from app.config.settings import get_settings
from spreadsheet_fixture_helpers import (
    make_boundary_xlsx_bytes,
    make_formula_heavy_xlsx_bytes,
    make_merged_range_heavy_xlsx_bytes,
    make_openpyxl_xlsx_bytes,
    make_privacy_xlsx_bytes,
    make_table_heavy_xlsx_bytes,
)


FIXTURES = Path(__file__).parent / "fixtures"
VALID_IMAGE = FIXTURES / "images" / "valid" / "fictional_form.png"
BLURRY_IMAGE = FIXTURES / "images" / "blurry" / "img_003_blurry_form.png"
TEXT_PDF = FIXTURES / "pdfs" / "text" / "pdf_001_text_based.pdf"
SCANNED_PDF = FIXTURES / "pdfs" / "scanned" / "pdf_002_scanned.pdf"
MIXED_PDF = FIXTURES / "pdfs" / "mixed" / "pdf_003_mixed.pdf"
SPREADSHEET_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class StaticOCRProvider:
    def __init__(self, text: str) -> None:
        self.text = text

    def extract_text(self, image_content: bytes) -> OCRResult:
        return OCRResult(status=OCRStatus.SUCCESS, text=self.text)


def make_pdf_bytes() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def measure(label: str, measurements: dict[str, float], operation) -> object:
    start = perf_counter()
    result = operation()
    measurements[label] = perf_counter() - start
    return result


def assert_measurements_recorded(
    measurements: dict[str, float],
    expected_labels: set[str],
) -> None:
    assert set(measurements) == expected_labels
    assert all(duration >= 0 for duration in measurements.values())


def measure_spreadsheet_pipeline(content: bytes, filename: str) -> dict[str, float]:
    measurements: dict[str, float] = {}
    parser = OpenPyXLSpreadsheetParser()
    settings = get_settings()

    inspection = measure(
        "workbook_inspection",
        measurements,
        lambda: parser.inspect(content, filename),
    )
    assert inspection.status == SpreadsheetInspectionStatus.SUCCESS
    assert inspection.workbook is not None

    spreadsheet_content = measure(
        "normalization",
        measurements,
        lambda: build_spreadsheet_content(inspection.workbook, settings=settings),
    )
    preview = measure(
        "preview_generation",
        measurements,
        lambda: build_spreadsheet_preview(spreadsheet_content),
    )
    combined_text_projection = measure(
        "combined_text_generation",
        measurements,
        lambda: build_spreadsheet_text_projection(spreadsheet_content),
    )
    end_to_end_result = measure(
        "total_input_processor",
        measurements,
        lambda: processors.process_input(
            InputRequest(
                attachments=[
                    Attachment(
                        filename=filename,
                        media_type=SPREADSHEET_MEDIA_TYPE,
                        content=content,
                    )
                ],
            ),
        ),
    )

    assert spreadsheet_content.workbook_name == filename
    assert preview
    assert combined_text_projection
    assert end_to_end_result.success is True
    assert end_to_end_result.normalized_input is not None
    assert end_to_end_result.normalized_input.spreadsheet_content
    return measurements


@pytest.mark.parametrize(
    ("label", "attachment"),
    [
        (
            "clear_image_validation",
            Attachment(
                filename="clear.png",
                media_type="image/png",
                content=VALID_IMAGE.read_bytes(),
            ),
        ),
        (
            "difficult_image_validation",
            Attachment(
                filename="blurry.png",
                media_type="image/png",
                content=BLURRY_IMAGE.read_bytes(),
            ),
        ),
        (
            "text_pdf_validation",
            Attachment(
                filename="text.pdf",
                media_type="application/pdf",
                content=TEXT_PDF.read_bytes(),
            ),
        ),
    ],
)
def test_measure_validation_time(label: str, attachment: Attachment) -> None:
    measurements: dict[str, float] = {}

    validated = measure(label, measurements, lambda: validate_attachment_modality(attachment))

    assert validated.attachment.filename == attachment.filename
    assert_measurements_recorded(measurements, {label})


def test_measure_image_ocr_and_total_processing_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    measurements: dict[str, float] = {}

    def fake_process_image_attachment(validated_attachment, ocr_provider):
        return measure(
            "image_ocr",
            measurements,
            lambda: ImageProcessingResult(
                image_content=ImageContent(
                    image_name=validated_attachment.attachment.filename,
                    extracted_text="clear image text",
                    preview="clear image text",
                )
            ),
        )

    monkeypatch.setattr(processors, "process_image_attachment", fake_process_image_attachment)

    result = measure(
        "total_input_processor",
        measurements,
        lambda: processors.process_input(
            InputRequest(
                attachments=[
                    Attachment(
                        filename="clear.png",
                        media_type="image/png",
                        content=VALID_IMAGE.read_bytes(),
                    )
                ],
            ),
            ocr_provider=StaticOCRProvider("clear image text"),
        ),
    )

    assert result.success is True
    assert_measurements_recorded(measurements, {"image_ocr", "total_input_processor"})


@pytest.mark.parametrize(
    ("label", "path"),
    [
        ("text_pdf_inspection", TEXT_PDF),
        ("scanned_pdf_inspection", SCANNED_PDF),
        ("mixed_pdf_inspection", MIXED_PDF),
    ],
)
def test_measure_pdf_inspection_time(label: str, path: Path) -> None:
    measurements: dict[str, float] = {}

    result = measure(label, measurements, lambda: classify_pdf_content(path.read_bytes()))

    assert result.document_type in {
        PDFDocumentType.TEXT_BASED,
        PDFDocumentType.SCANNED,
        PDFDocumentType.MIXED,
    }
    assert_measurements_recorded(measurements, {label})


def test_measure_pdf_extraction_and_total_processing_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    measurements: dict[str, float] = {}

    def fake_process_pdf_attachment(
        validated_attachment,
        pdf_extractor,
        *,
        ocr_provider=None,
        page_image_extractor=None,
    ):
        return measure(
            "pdf_extraction",
            measurements,
            lambda: PDFProcessingResult(
                pdf_content=PDFContent(
                    pdf_name=validated_attachment.attachment.filename,
                    extracted_text="pdf text",
                    preview="pdf text",
                )
            ),
        )

    monkeypatch.setattr(processors, "process_pdf_attachment", fake_process_pdf_attachment)

    result = measure(
        "total_input_processor",
        measurements,
        lambda: processors.process_input(
            InputRequest(
                attachments=[
                    Attachment(
                        filename="document.pdf",
                        media_type="application/pdf",
                        content=make_pdf_bytes(),
                    )
                ],
            )
        ),
    )

    assert result.success is True
    assert_measurements_recorded(measurements, {"pdf_extraction", "total_input_processor"})


def test_measure_pii_detection_and_normalization_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    measurements: dict[str, float] = {}

    def fake_process_pdf_attachment(
        validated_attachment,
        pdf_extractor,
        *,
        ocr_provider=None,
        page_image_extractor=None,
    ):
        masked_text = measure(
            "pii_detection",
            measurements,
            lambda: mask_pii_in_text("Applicant PAN ABCDE1234F").text,
        )
        return PDFProcessingResult(
            pdf_content=PDFContent(
                pdf_name=validated_attachment.attachment.filename,
                extracted_text=masked_text,
                preview=masked_text,
            )
        )

    monkeypatch.setattr(processors, "process_pdf_attachment", fake_process_pdf_attachment)

    result = measure(
        "normalization",
        measurements,
        lambda: processors.process_input(
            InputRequest(
                user_query="Mask this.",
                attachments=[
                    Attachment(
                        filename="document.pdf",
                        media_type="application/pdf",
                        content=make_pdf_bytes(),
                    )
                ],
            )
        ),
    )

    assert result.success is True
    assert result.normalized_input is not None
    assert "ABCDE1234F" not in result.normalized_input.combined_text
    assert_measurements_recorded(measurements, {"pii_detection", "normalization"})


@pytest.mark.parametrize(
    ("case_name", "filename", "content"),
    [
        ("small_workbook", "small.xlsx", make_openpyxl_xlsx_bytes()),
        ("five_visible_sheets_50x50", "boundary.xlsx", make_boundary_xlsx_bytes()),
        ("formula_heavy", "formulas.xlsx", make_formula_heavy_xlsx_bytes()),
        ("table_heavy", "tables.xlsx", make_table_heavy_xlsx_bytes()),
        ("merged_range_heavy", "merged.xlsx", make_merged_range_heavy_xlsx_bytes()),
        ("long_cell", "long-cell.xlsx", make_privacy_xlsx_bytes(long_text_length=5001)),
        ("pii_heavy", "pii.xlsx", make_privacy_xlsx_bytes(long_text_length=100)),
    ],
    ids=[
        "small_workbook",
        "five_visible_sheets_50x50",
        "formula_heavy",
        "table_heavy",
        "merged_range_heavy",
        "long_cell",
        "pii_heavy",
    ],
)
def test_measure_representative_spreadsheet_processing_time(
    case_name: str,
    filename: str,
    content: bytes,
) -> None:
    measurements = measure_spreadsheet_pipeline(content, filename)

    assert_measurements_recorded(
        measurements,
        {
            "workbook_inspection",
            "normalization",
            "preview_generation",
            "combined_text_generation",
            "total_input_processor",
        },
    )
    assert case_name


def test_measure_multiple_attachment_total_processing_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    measurements: dict[str, float] = {}

    def fake_process_image_attachment(validated_attachment, ocr_provider):
        filename = validated_attachment.attachment.filename
        return ImageProcessingResult(
            image_content=ImageContent(
                image_name=filename,
                extracted_text=f"{filename} text",
                preview=f"{filename} text",
            )
        )

    def fake_process_pdf_attachment(
        validated_attachment,
        pdf_extractor,
        *,
        ocr_provider=None,
        page_image_extractor=None,
    ):
        filename = validated_attachment.attachment.filename
        return PDFProcessingResult(
            pdf_content=PDFContent(
                pdf_name=filename,
                extracted_text=f"{filename} text",
                preview=f"{filename} text",
            )
        )

    monkeypatch.setattr(processors, "process_image_attachment", fake_process_image_attachment)
    monkeypatch.setattr(processors, "process_pdf_attachment", fake_process_pdf_attachment)

    result = measure(
        "multiple_attachments_total",
        measurements,
        lambda: processors.process_input(
            InputRequest(
                user_query="Multiple attachments",
                attachments=[
                    Attachment(
                        filename="clear.png",
                        media_type="image/png",
                        content=VALID_IMAGE.read_bytes(),
                    ),
                    Attachment(
                        filename="document.pdf",
                        media_type="application/pdf",
                        content=make_pdf_bytes(),
                    ),
                ],
            ),
            ocr_provider=StaticOCRProvider("clear image text"),
        ),
    )

    assert result.success is True
    assert_measurements_recorded(measurements, {"multiple_attachments_total"})
