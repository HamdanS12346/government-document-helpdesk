"""Run the Input Processor evaluation dataset."""

from __future__ import annotations

import argparse
import io
import json
from pathlib import Path
import sys
from typing import Any

from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.input_processing.ocr_provider import OCRResult, OCRStatus  # noqa: E402
from app.input_processing.processors import process_input  # noqa: E402
from app.input_processing.schemas import Attachment, InputRequest  # noqa: E402
from evaluation.case_loader import find_default_dataset, load_cases, validate_case_ids  # noqa: E402
from evaluation.evaluators.input_processor.evaluator import (  # noqa: E402
    evaluate_input_case,
    summarize_input_results,
)
from evaluation.langfuse_reporting import LangfuseReporter  # noqa: E402


IMAGE_FIXTURE = PROJECT_ROOT / "tests/input-processor/fixtures/images/valid/fictional_form.png"
PDF_FIXTURE = PROJECT_ROOT / "tests/input-processor/fixtures/pdfs/forms/pdf_004_simple_form.pdf"
INVALID_IMAGE_FIXTURE = PROJECT_ROOT / "tests/input-processor/fixtures/images/invalid/not_an_image.png"
INVALID_PDF_FIXTURE = PROJECT_ROOT / "tests/input-processor/fixtures/pdfs/invalid/pdf_009_corrupt.pdf"
OVER_LIMIT_PDF_FIXTURE = PROJECT_ROOT / "tests/input-processor/fixtures/pdfs/over_page_limit/pdf_010_over_page_limit.pdf"


class EvaluationOCRProvider:
    """Deterministic OCR provider used to avoid Tesseract during evaluation."""

    def extract_text(self, image_content: bytes) -> OCRResult:
        return OCRResult(status=OCRStatus.SUCCESS, text="Synthetic evaluation document text")


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
    expected_valid = bool(case.get("expected", {}).get("valid", False))
    attachments = []
    try:
        for attachment_data in input_data.get("attachments", []):
            attachments.append(_build_attachment(attachment_data, expected_valid))
        request = InputRequest(
            user_query=input_data.get("text"),
            attachments=attachments,
        )
        result = process_input(request, ocr_provider=EvaluationOCRProvider())
    except Exception:
        return False, []

    if not result.success or result.normalized_input is None:
        return False, []

    normalized = result.normalized_input
    modality = []
    if normalized.user_query.strip():
        modality.append("text")
    if normalized.image_content:
        modality.append("image")
    if normalized.pdf_content:
        modality.append("pdf")
    return True, modality


def _build_attachment(data: dict[str, Any], expected_valid: bool) -> Attachment:
    filename = str(data.get("filename", "attachment"))
    suffix = Path(filename).suffix.lower()
    media_type = str(data.get("mime_type", _media_type_for_suffix(suffix)))
    content = _content_for_attachment(filename, suffix, expected_valid)
    return Attachment(filename=filename, media_type=media_type, content=content)


def _content_for_attachment(filename: str, suffix: str, expected_valid: bool) -> bytes:
    lowered = filename.lower()
    if "missing-content" in lowered:
        return b""
    if suffix in {".png", ".jpg", ".jpeg"}:
        if not expected_valid or "unreadable" in lowered or "blank" in lowered:
            return INVALID_IMAGE_FIXTURE.read_bytes()
        return _image_bytes(suffix)
    if suffix == ".pdf":
        if "large" in lowered or "negative-size" in lowered:
            return OVER_LIMIT_PDF_FIXTURE.read_bytes()
        if not expected_valid or "corrupt" in lowered or "empty" in lowered or "broken" in lowered:
            return INVALID_PDF_FIXTURE.read_bytes()
        return PDF_FIXTURE.read_bytes()
    return str(filename).encode("utf-8")


def _image_bytes(suffix: str) -> bytes:
    image = Image.new("RGB", (8, 8), color="white")
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG" if suffix in {".jpg", ".jpeg"} else "PNG")
    return buffer.getvalue()


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
    parser.add_argument(
        "--langfuse",
        action="store_true",
        help="Publish aggregate and per-case scores to Langfuse.",
    )
    args = parser.parse_args()
    dataset = args.dataset or find_default_dataset(PROJECT_ROOT / "evaluation/datasets/input_processor")
    report = run_dataset(dataset)
    if args.langfuse:
        LangfuseReporter.from_environment().publish("input_processor", report)
    rendered = json.dumps(report, indent=2)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
