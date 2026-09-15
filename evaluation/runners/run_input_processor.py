"""Run the Input Processor evaluation dataset."""

from __future__ import annotations

import argparse
import io
import json
from pathlib import Path
import sys
from typing import Any

from PIL import Image
from pypdf import PdfReader, PdfWriter

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.input_processing.ocr_provider import OCRResult, OCRStatus  # noqa: E402
from app.input_processing.pdf_processor import (  # noqa: E402
    PDFExtractionResult,
    PDFExtractionStatus,
    classify_pdf_content,
)
from app.input_processing.processors import process_input  # noqa: E402
from app.input_processing.schemas import Attachment, InputRequest  # noqa: E402
from evaluation.case_loader import find_default_dataset, load_cases, validate_case_ids  # noqa: E402
from evaluation.evaluators.input_processor.evaluator import (  # noqa: E402
    evaluate_input_case,
    summarize_input_results,
)
from evaluation.langfuse_reporting import LangfuseReporter  # noqa: E402


FIXTURE_ROOT = PROJECT_ROOT / "evaluation/fixtures/input_processor"
IMAGE_FIXTURES = (
    FIXTURE_ROOT / "images/source1.jpg",
    FIXTURE_ROOT / "images/source2.jpg",
)
PDF_FIXTURES = (
    FIXTURE_ROOT / "pdfs/source1.pdf",
    FIXTURE_ROOT / "pdfs/source2.pdf",
)


class EvaluationOCRProvider:
    """Deterministic OCR provider used to avoid Tesseract during evaluation."""

    def extract_text(self, image_content: bytes) -> OCRResult:
        return OCRResult(status=OCRStatus.SUCCESS, text="Synthetic evaluation document text")


class EvaluationPDFExtractor:
    """Use the Input Processor's PDF classification on fixture-derived samples."""

    def extract(self, pdf_content: bytes) -> PDFExtractionResult:
        classification = classify_pdf_content(pdf_content)
        return PDFExtractionResult(
            status=PDFExtractionStatus.SUCCESS,
            document_type=classification.document_type,
            pages=classification.pages,
        )


def run_dataset(dataset_path: Path) -> dict[str, Any]:
    cases = load_cases(dataset_path)
    validate_case_ids(cases)
    results = []
    for case in cases:
        actual_valid, actual_modality = _run_case(case)
        results.append(
            evaluate_input_case(
                case,
                actual_valid=actual_valid,
                actual_modality=actual_modality,
            )
        )
    return {"metrics": summarize_input_results(results), "cases": results}


def _run_case(case: dict[str, Any]) -> tuple[bool, list[str]]:
    input_data = case.get("input", {})
    attachments = []
    try:
        for index, attachment_data in enumerate(input_data.get("attachments", [])):
            attachments.append(_build_attachment(attachment_data, index))
        request = InputRequest(
            user_query=input_data.get("text"),
            attachments=attachments,
        )
        result = process_input(
            request,
            ocr_provider=EvaluationOCRProvider(),
            pdf_extractor=EvaluationPDFExtractor(),
        )
    except Exception:
        return False, []

    actual_valid = result.success and all(
        status.status == "success" for status in result.attachment_statuses
    )
    if result.normalized_input is None:
        return actual_valid, []

    normalized = result.normalized_input
    modality = []
    if normalized.user_query.strip():
        modality.append("text")
    if normalized.image_content:
        modality.append("image")
    if normalized.pdf_content:
        modality.append("pdf")
    return actual_valid, modality


def _build_attachment(data: dict[str, Any], index: int) -> Attachment:
    filename = data.get("filename", "")
    suffix = Path(filename).suffix.lower()
    media_type = data.get("mime_type", "")
    if media_type:
        media_type = str(media_type)
    content = _content_for_attachment(data, suffix, index)
    return Attachment(filename=filename, media_type=media_type, content=content)


def _content_for_attachment(data: dict[str, Any], suffix: str, index: int) -> bytes:
    filename = str(data.get("filename", "attachment"))
    lowered = filename.lower()
    if "missing-content" in lowered:
        return b""
    if suffix in {".png", ".jpg", ".jpeg"}:
        return _load_image_fixture(index, suffix)
    if suffix == ".pdf":
        return _load_pdf_fixture(index)
    return str(filename).encode("utf-8")


def _load_image_fixture(index: int, suffix: str) -> bytes:
    fixture = IMAGE_FIXTURES[index % len(IMAGE_FIXTURES)]
    if suffix in {".jpg", ".jpeg"}:
        return fixture.read_bytes()

    image = Image.open(fixture).convert("RGB")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _load_pdf_fixture(index: int) -> bytes:
    """Load real fixture PDF bytes and retain at most five real source pages."""

    fixture = PDF_FIXTURES[index % len(PDF_FIXTURES)]
    reader = PdfReader(io.BytesIO(fixture.read_bytes()))
    writer = PdfWriter()
    page_numbers = range(1, 5) if fixture.name == "source1.pdf" else range(0, 5)
    for page_number in page_numbers:
        writer.add_page(reader.pages[page_number])
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def _media_type_for_suffix(suffix: str) -> str:
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".pdf": "application/pdf",
    }.get(suffix, "application/octet-stream")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    langfuse_group = parser.add_mutually_exclusive_group()
    langfuse_group.add_argument(
        "--langfuse",
        action="store_true",
        help="Publish results to Langfuse (the default).",
    )
    langfuse_group.add_argument(
        "--no-langfuse",
        action="store_true",
        help="Skip Langfuse publishing for this run.",
    )
    args = parser.parse_args()
    dataset = args.dataset or find_default_dataset(PROJECT_ROOT / "evaluation/datasets/input_processor")
    report = run_dataset(dataset)
    if not args.no_langfuse:
        LangfuseReporter.from_environment().publish("input_processor", report)
    rendered = json.dumps(report, indent=2)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
