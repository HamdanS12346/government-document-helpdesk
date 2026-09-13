"""PDF fixture coverage for the Input Processor."""

from pathlib import Path

import pytest

from app.input_processing.errors import InputProcessingError, InputProcessingErrorCode
from app.input_processing.pdf_processor import (
    MAX_PDF_PAGE_COUNT,
    PDFDocumentType,
    classify_pdf_content,
    get_pdf_page_count,
    validate_pdf_page_count,
)


FIXTURES = Path(__file__).parent / "fixtures" / "pdfs"


PDF_FIXTURES = {
    "PDF-001": FIXTURES / "text" / "pdf_001_text_based.pdf",
    "PDF-002": FIXTURES / "scanned" / "pdf_002_scanned.pdf",
    "PDF-003": FIXTURES / "mixed" / "pdf_003_mixed.pdf",
    "PDF-004": FIXTURES / "forms" / "pdf_004_simple_form.pdf",
    "PDF-005": FIXTURES / "tables" / "pdf_005_table.pdf",
    "PDF-006": FIXTURES / "pii" / "pdf_006_fictional_pii.pdf",
    "PDF-007": FIXTURES / "instructions" / "pdf_007_legitimate_instructions.pdf",
    "PDF-008": FIXTURES / "injection" / "pdf_008_ai_directed_text.pdf",
    "PDF-009": FIXTURES / "invalid" / "pdf_009_corrupt.pdf",
    "PDF-010": FIXTURES / "over_page_limit" / "pdf_010_over_page_limit.pdf",
}


@pytest.mark.parametrize("fixture_path", PDF_FIXTURES.values(), ids=PDF_FIXTURES.keys())
def test_required_pdf_fixture_exists(fixture_path: Path) -> None:
    assert fixture_path.exists()
    assert fixture_path.stat().st_size > 0


@pytest.mark.parametrize(
    "fixture_path",
    [
        PDF_FIXTURES["PDF-001"],
        PDF_FIXTURES["PDF-004"],
        PDF_FIXTURES["PDF-005"],
        PDF_FIXTURES["PDF-006"],
        PDF_FIXTURES["PDF-007"],
        PDF_FIXTURES["PDF-008"],
    ],
)
def test_text_based_pdf_fixtures_have_extractable_text(fixture_path: Path) -> None:
    result = classify_pdf_content(fixture_path.read_bytes())

    assert result.document_type == PDFDocumentType.TEXT_BASED
    assert any(page.text.strip() for page in result.pages)


def test_scanned_pdf_fixture_classifies_as_scanned() -> None:
    result = classify_pdf_content(PDF_FIXTURES["PDF-002"].read_bytes())

    assert result.document_type == PDFDocumentType.SCANNED
    assert all(not page.text.strip() for page in result.pages)


def test_mixed_pdf_fixture_classifies_as_mixed() -> None:
    result = classify_pdf_content(PDF_FIXTURES["PDF-003"].read_bytes())

    assert result.document_type == PDFDocumentType.MIXED
    assert any(page.text.strip() for page in result.pages)
    assert any(not page.text.strip() for page in result.pages)


def test_corrupt_pdf_fixture_returns_controlled_failure() -> None:
    with pytest.raises(InputProcessingError) as exc_info:
        get_pdf_page_count(PDF_FIXTURES["PDF-009"].read_bytes())

    assert exc_info.value.code == InputProcessingErrorCode.UNREADABLE_CONTENT


def test_pdf_page_limit_fixtures_cover_below_at_and_above_limit() -> None:
    below_limit = FIXTURES / "over_page_limit" / "below_limit_4_pages.pdf"
    at_limit = FIXTURES / "over_page_limit" / "at_limit_5_pages.pdf"
    over_limit = PDF_FIXTURES["PDF-010"]

    assert get_pdf_page_count(below_limit.read_bytes()) == MAX_PDF_PAGE_COUNT - 1
    assert get_pdf_page_count(at_limit.read_bytes()) == MAX_PDF_PAGE_COUNT
    assert get_pdf_page_count(over_limit.read_bytes()) == MAX_PDF_PAGE_COUNT + 1

    validate_pdf_page_count(below_limit.read_bytes())
    validate_pdf_page_count(at_limit.read_bytes())
    with pytest.raises(InputProcessingError) as exc_info:
        validate_pdf_page_count(over_limit.read_bytes())

    assert exc_info.value.code == InputProcessingErrorCode.PDF_PAGE_LIMIT_EXCEEDED
