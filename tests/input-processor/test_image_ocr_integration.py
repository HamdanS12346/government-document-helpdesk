"""Real OCR provider integration tests for image processing."""

from pathlib import Path
import shutil

import pytest

from app.input_processing.image_processor import process_image_attachment
from app.input_processing.ocr_provider import OCRStatus, TesseractOCRProvider
from app.input_processing.schemas import Attachment, InputModality, ValidatedAttachment


FIXTURES = Path(__file__).parent / "fixtures"
VALID_IMAGES = [
    FIXTURES / "images" / "valid" / "fictional_form.png",
    FIXTURES / "images" / "valid" / "fictional_form.jpg",
]

pytestmark = pytest.mark.skipif(
    shutil.which("tesseract") is None,
    reason="Tesseract OCR executable is not available on PATH.",
)


@pytest.mark.parametrize("image_path", VALID_IMAGES)
def test_tesseract_provider_extracts_meaningful_text_from_clear_fixture(
    image_path: Path,
) -> None:
    result = TesseractOCRProvider(timeout_seconds=5).extract_text(image_path.read_bytes())

    assert result.status == OCRStatus.SUCCESS
    assert "fictional" in result.text.lower()
    assert any(token in result.text.lower() for token in ["form", "a100"])


def test_image_processor_accepts_real_tesseract_provider_for_clear_png() -> None:
    image_path = FIXTURES / "images" / "valid" / "fictional_form.png"
    validated = ValidatedAttachment(
        attachment=Attachment(
            filename=image_path.name,
            media_type="image/png",
            content=image_path.read_bytes(),
        ),
        modality=InputModality.PNG,
    )

    result = process_image_attachment(
        validated,
        TesseractOCRProvider(timeout_seconds=5),
    )

    assert result.error is None
    assert result.image_content is not None
    assert result.image_content.image_name == image_path.name
    assert "fictional" in result.image_content.extracted_text.lower()
    assert result.image_content.preview == result.image_content.extracted_text[:500]
