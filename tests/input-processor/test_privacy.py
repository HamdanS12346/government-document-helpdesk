"""Privacy boundary tests for the Input Processor."""

import logging
from io import BytesIO
from pathlib import Path

from pypdf import PdfWriter

from app.contracts.normalized_input import NormalizedInput
from app.graph.state import GraphState
from app.input_processing import processors
from app.input_processing.image_processor import process_image_attachment
from app.input_processing.ocr_provider import OCRResult, OCRStatus
from app.input_processing.pdf_processor import (
    PDFClassificationResult,
    PDFDocumentType,
    PDFExtractionResult,
    PDFExtractionStatus,
    PDFPageText,
    PendingPDFExtractor,
    process_pdf_attachment,
)
from app.input_processing.processors import build_graph_state_update, process_input
from app.input_processing.schemas import Attachment, InputModality, InputRequest, ValidatedAttachment


FIXTURES = Path(__file__).parent / "fixtures"
VALID_IMAGE = FIXTURES / "images" / "valid" / "fictional_form.png"


class StaticOCRProvider:
    def __init__(self, text: str) -> None:
        self.text = text

    def extract_text(self, image_content: bytes) -> OCRResult:
        return OCRResult(status=OCRStatus.SUCCESS, text=self.text)


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


def make_validated_pdf(raw_bytes: bytes | None = None) -> ValidatedAttachment:
    return ValidatedAttachment(
        attachment=Attachment(
            filename="synthetic.pdf",
            media_type="application/pdf",
            content=raw_bytes or make_pdf_bytes(),
        ),
        modality=InputModality.PDF,
    )


def test_image_processing_result_does_not_include_raw_image_bytes() -> None:
    raw_bytes = VALID_IMAGE.read_bytes()
    validated = ValidatedAttachment(
        attachment=Attachment(
            filename="fictional_form.png",
            media_type="image/png",
            content=raw_bytes,
        ),
        modality=InputModality.PNG,
    )

    result = process_image_attachment(
        validated,
        StaticOCRProvider("Synthetic form text"),
    )

    payload = result.model_dump(mode="json")

    assert "content" not in payload
    assert "raw" not in payload
    assert str(raw_bytes) not in str(payload)


def test_image_processing_masks_pii_before_result_or_preview() -> None:
    result = process_image_attachment(
        make_validated_image(),
        StaticOCRProvider("Applicant PAN ABCDE1234F phone 9876543210"),
    )

    payload = result.model_dump(mode="json")

    assert "ABCDE1234F" not in str(payload)
    assert "9876543210" not in str(payload)
    assert "[REDACTED]" in str(payload)


def test_image_processing_does_not_log_raw_ocr_text_or_pii(caplog) -> None:
    caplog.set_level(logging.DEBUG)

    process_image_attachment(
        make_validated_image(),
        StaticOCRProvider("Applicant PAN ABCDE1234F phone 9876543210"),
    )

    log_output = caplog.text

    assert "ABCDE1234F" not in log_output
    assert "9876543210" not in log_output
    assert "Applicant PAN" not in log_output


def test_image_processing_normalized_content_does_not_put_raw_bytes_in_state_like_payload() -> None:
    raw_bytes = VALID_IMAGE.read_bytes()
    result = process_image_attachment(
        make_validated_image(),
        StaticOCRProvider("Applicant PAN ABCDE1234F"),
    )

    assert result.image_content is not None

    normalized_input = NormalizedInput(
        user_query="",
        image_content=[result.image_content],
        pdf_content=[],
        combined_text=result.image_content.extracted_text,
    )
    state: GraphState = {"normalized_input": normalized_input}
    state_payload = str(state)

    assert "attachment" not in state_payload
    assert "raw_attachment_bytes" not in state_payload
    assert "raw_image_bytes" not in state_payload
    assert str(raw_bytes) not in state_payload
    assert "ABCDE1234F" not in state_payload
    assert "[REDACTED]" in state_payload


def test_image_processing_trace_like_payload_excludes_raw_ocr_text_and_unmasked_pii() -> None:
    result = process_image_attachment(
        make_validated_image(),
        StaticOCRProvider("Applicant PAN ABCDE1234F phone 9876543210"),
    )

    assert result.image_content is not None

    trace_payload = {
        "modality": "image",
        "processing_status": "success",
        "image_name": result.image_content.image_name,
        "preview": result.image_content.preview,
    }

    assert "ABCDE1234F" not in str(trace_payload)
    assert "9876543210" not in str(trace_payload)
    assert "[REDACTED]" in str(trace_payload)


def test_pdf_processing_result_does_not_include_raw_pdf_bytes(monkeypatch) -> None:
    raw_bytes = make_pdf_bytes()

    def fake_classify_pdf_content(pdf_content: bytes) -> PDFClassificationResult:
        return PDFClassificationResult(
            document_type=PDFDocumentType.TEXT_BASED,
            pages=[PDFPageText(page_number=1, text="Synthetic PDF text")],
        )

    monkeypatch.setattr(
        "app.input_processing.pdf_processor.classify_pdf_content",
        fake_classify_pdf_content,
    )

    result = process_pdf_attachment(make_validated_pdf(raw_bytes), PendingPDFExtractor())
    payload = result.model_dump(mode="json")

    assert "content" not in payload
    assert "raw" not in payload
    assert str(raw_bytes) not in str(payload)


def test_pdf_processing_masks_pii_before_result_or_preview(monkeypatch) -> None:
    def fake_classify_pdf_content(pdf_content: bytes) -> PDFClassificationResult:
        return PDFClassificationResult(
            document_type=PDFDocumentType.TEXT_BASED,
            pages=[PDFPageText(page_number=1, text="PAN ABCDE1234F phone 9876543210")],
        )

    monkeypatch.setattr(
        "app.input_processing.pdf_processor.classify_pdf_content",
        fake_classify_pdf_content,
    )

    result = process_pdf_attachment(make_validated_pdf(), PendingPDFExtractor())
    payload = result.model_dump(mode="json")

    assert "ABCDE1234F" not in str(payload)
    assert "9876543210" not in str(payload)
    assert "[REDACTED]" in str(payload)


def test_pdf_processing_does_not_log_raw_extracted_text_or_pii(caplog, monkeypatch) -> None:
    caplog.set_level(logging.DEBUG)

    def fake_classify_pdf_content(pdf_content: bytes) -> PDFClassificationResult:
        return PDFClassificationResult(
            document_type=PDFDocumentType.TEXT_BASED,
            pages=[PDFPageText(page_number=1, text="Applicant PAN ABCDE1234F")],
        )

    monkeypatch.setattr(
        "app.input_processing.pdf_processor.classify_pdf_content",
        fake_classify_pdf_content,
    )

    process_pdf_attachment(make_validated_pdf(), PendingPDFExtractor())

    log_output = caplog.text

    assert "ABCDE1234F" not in log_output
    assert "Applicant PAN" not in log_output


def test_pdf_processing_normalized_content_does_not_put_raw_bytes_in_state_like_payload(
    monkeypatch,
) -> None:
    raw_bytes = make_pdf_bytes()

    def fake_classify_pdf_content(pdf_content: bytes) -> PDFClassificationResult:
        return PDFClassificationResult(
            document_type=PDFDocumentType.TEXT_BASED,
            pages=[PDFPageText(page_number=1, text="Applicant PAN ABCDE1234F")],
        )

    monkeypatch.setattr(
        "app.input_processing.pdf_processor.classify_pdf_content",
        fake_classify_pdf_content,
    )

    result = process_pdf_attachment(make_validated_pdf(raw_bytes), PendingPDFExtractor())

    assert result.pdf_content is not None

    normalized_input = NormalizedInput(
        user_query="",
        image_content=[],
        pdf_content=[result.pdf_content],
        combined_text=result.pdf_content.extracted_text,
    )
    state: GraphState = {"normalized_input": normalized_input}
    state_payload = str(state)

    assert "attachment" not in state_payload
    assert "raw_attachment_bytes" not in state_payload
    assert "raw_pdf_bytes" not in state_payload
    assert str(raw_bytes) not in state_payload
    assert "ABCDE1234F" not in state_payload
    assert "[REDACTED]" in state_payload


def test_failed_pdf_extraction_does_not_leak_provider_text_or_raw_bytes(monkeypatch) -> None:
    raw_bytes = make_pdf_bytes()

    def fake_classify_pdf_content(pdf_content: bytes) -> PDFClassificationResult:
        return PDFClassificationResult(
            document_type=PDFDocumentType.MIXED,
            pages=[
                PDFPageText(page_number=1, text=""),
                PDFPageText(page_number=2, text="Machine text"),
            ],
        )

    monkeypatch.setattr(
        "app.input_processing.pdf_processor.classify_pdf_content",
        fake_classify_pdf_content,
    )

    result = process_pdf_attachment(make_validated_pdf(raw_bytes), PendingPDFExtractor())
    payload = result.model_dump(mode="json")

    assert result.error is not None
    assert result.pdf_content is None
    assert result.extraction_result is None
    assert "Machine text" not in str(payload)
    assert str(raw_bytes) not in str(payload)


def test_public_processor_does_not_put_raw_uploads_in_graph_state() -> None:
    raw_upload = b"synthetic raw private upload bytes"
    result = process_input(
        InputRequest(
            user_query="Use the text only.",
            attachments=[
                Attachment(
                    filename="private.pdf",
                    media_type="application/pdf",
                    content=raw_upload,
                )
            ],
        )
    )

    state_update = build_graph_state_update(result)

    assert result.success is True
    assert state_update.keys() == {"normalized_input"}
    assert "synthetic raw private upload bytes" not in str(state_update)
    assert str(raw_upload) not in str(state_update)


def test_public_processor_does_not_log_raw_upload_or_extracted_pii(
    caplog,
    monkeypatch,
) -> None:
    caplog.set_level(logging.DEBUG)

    def fake_process_image_attachment(validated_attachment, ocr_provider):
        from app.contracts.normalized_input import ImageContent
        from app.input_processing.image_processor import ImageProcessingResult

        return ImageProcessingResult(
            image_content=ImageContent(
                image_name=validated_attachment.attachment.filename,
                extracted_text="Applicant PAN [REDACTED]",
                preview="Applicant PAN [REDACTED]",
            )
        )

    monkeypatch.setattr(processors, "process_image_attachment", fake_process_image_attachment)

    process_input(
        InputRequest(
            attachments=[
                Attachment(
                    filename="private.png",
                    media_type="image/png",
                    content=b"\x89PNG\r\n\x1a\nraw upload bytes ABCDE1234F",
                )
            ],
        ),
        ocr_provider=StaticOCRProvider("Applicant PAN ABCDE1234F"),
    )

    assert "raw upload bytes" not in caplog.text
    assert "ABCDE1234F" not in caplog.text
    assert "Applicant PAN" not in caplog.text


def test_public_processor_does_not_create_memory_or_storage_side_effects(
    monkeypatch,
) -> None:
    def forbidden_store(*args, **kwargs):
        raise AssertionError("uploads must not be persisted")

    monkeypatch.setattr(processors, "memory_store", forbidden_store, raising=False)
    monkeypatch.setattr(processors, "knowledge_store", forbidden_store, raising=False)
    monkeypatch.setattr(processors, "vector_store", forbidden_store, raising=False)

    result = process_input(InputRequest(user_query="No storage side effects."))

    assert result.success is True
    assert not hasattr(result, "memory_store")
    assert not hasattr(result, "knowledge_store")
    assert not hasattr(result, "vector_store")


def test_user_uploads_are_not_treated_as_authoritative_knowledge_documents(
    monkeypatch,
) -> None:
    def fake_process_pdf_attachment(
        validated_attachment,
        pdf_extractor,
        *,
        ocr_provider=None,
        page_image_extractor=None,
    ):
        from app.contracts.normalized_input import PDFContent
        from app.input_processing.pdf_processor import PDFProcessingResult

        return PDFProcessingResult(
            pdf_content=PDFContent(
                pdf_name=validated_attachment.attachment.filename,
                extracted_text="User supplied document text",
                preview="User supplied document text",
            )
        )

    monkeypatch.setattr(processors, "process_pdf_attachment", fake_process_pdf_attachment)

    result = process_input(
        InputRequest(
            attachments=[
                Attachment(
                    filename="upload.pdf",
                    media_type="application/pdf",
                    content=make_pdf_bytes(),
                )
            ],
        )
    )

    assert result.success is True
    assert result.normalized_input is not None
    assert result.normalized_input.pdf_content[0].pdf_name == "upload.pdf"
    assert not hasattr(result.normalized_input.pdf_content[0], "authoritative")
    assert not hasattr(result.normalized_input.pdf_content[0], "knowledge_base_id")
    assert not hasattr(result.normalized_input.pdf_content[0], "vector_id")
