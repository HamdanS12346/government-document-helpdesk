"""Real PDF provider integration tests for input processing."""

from io import BytesIO
from pathlib import Path

import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app.input_processing.errors import InputProcessingErrorCode
from app.input_processing.pdf_processor import (
    PDFDocumentType,
    PendingPDFExtractor,
    classify_pdf_content,
    get_pdf_page_count,
    process_pdf_attachment,
)
from app.input_processing.preview import PDF_PREVIEW_CHARACTERS_PER_PAGE
from app.input_processing.schemas import Attachment, InputModality, ValidatedAttachment


FIXTURES = Path(__file__).parent / "fixtures"
INVALID_PDF = FIXTURES / "pdfs" / "invalid" / "not_a_pdf.pdf"


def make_text_pdf_bytes(text: str) -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    stream = DecodedStreamObject()
    stream.set_data(f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("ascii"))
    page[NameObject("/Contents")] = stream
    page[NameObject("/Resources")] = DictionaryObject(
        {
            NameObject("/Font"): DictionaryObject(
                {
                    NameObject("/F1"): DictionaryObject(
                        {
                            NameObject("/Type"): NameObject("/Font"),
                            NameObject("/Subtype"): NameObject("/Type1"),
                            NameObject("/BaseFont"): NameObject("/Helvetica"),
                        }
                    )
                }
            )
        }
    )
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def make_validated_pdf(content: bytes, filename: str = "synthetic-text.pdf") -> ValidatedAttachment:
    return ValidatedAttachment(
        attachment=Attachment(
            filename=filename,
            media_type="application/pdf",
            content=content,
        ),
        modality=InputModality.PDF,
    )


def test_real_pypdf_extracts_meaningful_text_from_synthetic_text_pdf() -> None:
    pdf_bytes = make_text_pdf_bytes("Fictional permit application A100")

    reader = PdfReader(BytesIO(pdf_bytes))
    extracted_text = reader.pages[0].extract_text()

    assert extracted_text is not None
    assert "Fictional permit application" in extracted_text


def test_pdf_processor_classifies_real_text_pdf_as_text_based() -> None:
    pdf_bytes = make_text_pdf_bytes("Fictional benefit notice B200")

    result = classify_pdf_content(pdf_bytes)

    assert result.document_type == PDFDocumentType.TEXT_BASED
    assert len(result.pages) == 1
    assert "Fictional benefit notice" in result.pages[0].text


def test_pdf_processor_builds_pdf_content_with_real_text_pdf() -> None:
    pdf_bytes = make_text_pdf_bytes("Fictional certificate request C300")

    result = process_pdf_attachment(
        make_validated_pdf(pdf_bytes),
        PendingPDFExtractor(),
    )

    assert result.error is None
    assert result.pdf_content is not None
    assert result.pdf_content.pdf_name == "synthetic-text.pdf"
    assert "Fictional certificate request" in result.pdf_content.extracted_text
    assert result.pdf_content.preview == result.pdf_content.extracted_text[
        :PDF_PREVIEW_CHARACTERS_PER_PAGE
    ]


def test_pdf_processor_returns_controlled_failure_for_real_invalid_pdf_fixture() -> None:
    result = process_pdf_attachment(
        make_validated_pdf(INVALID_PDF.read_bytes(), filename=INVALID_PDF.name),
        PendingPDFExtractor(),
    )

    assert result.pdf_content is None
    assert result.error is not None
    assert result.error.code == InputProcessingErrorCode.UNREADABLE_CONTENT


def test_real_pypdf_page_count_reads_generated_pdf() -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.add_blank_page(width=72, height=72)
    buffer = BytesIO()
    writer.write(buffer)

    assert get_pdf_page_count(buffer.getvalue()) == 2


@pytest.mark.skip(reason="Real scanned PDF rendering provider is not configured yet.")
def test_real_provider_scanned_pdf_integration_when_configured() -> None:
    raise AssertionError("Skipped until a real scanned PDF rendering provider is configured.")


@pytest.mark.skip(reason="Real mixed PDF fixture/provider is not configured yet.")
def test_real_provider_mixed_pdf_integration_when_configured() -> None:
    raise AssertionError("Skipped until a real mixed PDF provider fixture is configured.")
