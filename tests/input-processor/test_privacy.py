"""Privacy boundary tests for the Input Processor."""

import logging
from pathlib import Path

from app.contracts.normalized_input import NormalizedInput
from app.graph.state import GraphState
from app.input_processing.image_processor import process_image_attachment
from app.input_processing.ocr_provider import OCRResult, OCRStatus
from app.input_processing.schemas import Attachment, InputModality, ValidatedAttachment


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
