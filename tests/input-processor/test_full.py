r"""Manual full Input Processor runner.

Edit USER_TEXT and FILE_PATHS, then run:

    .\.venv\Scripts\python.exe tests\input-processor\test_full.py
"""

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from app.input_processing.processors import process_input  # noqa: E402
from app.input_processing.schemas import Attachment, InputRequest  # noqa: E402


USER_TEXT = "Please explain these documents."

FILE_PATHS = [
    "tests/input-processor/fixtures/images/test/test_image.png",
     "tests/input-processor/fixtures/pdfs/test/CertificateOfCompletion_DevOps Foundations Monitoring and Observability.pdf",
    # "tests/input-processor/fixtures/images/valid/fictional_form.png",
    # "tests/input-processor/fixtures/images/valid/fictional_form.jpg",
]


MEDIA_TYPES_BY_SUFFIX = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".pdf": "application/pdf",
}


def main() -> int:
    attachments = [_attachment_from_path(PROJECT_ROOT / path) for path in FILE_PATHS]
    request = InputRequest(user_query=USER_TEXT, attachments=attachments)
    result = process_input(request)

    if result.normalized_input is not None:
        print(result.normalized_input.model_dump_json(indent=2))
        return 0

    print(result.model_dump_json(indent=2))
    return 1


def _attachment_from_path(path: Path) -> Attachment:
    media_type = MEDIA_TYPES_BY_SUFFIX.get(path.suffix.lower())
    if media_type is None:
        raise ValueError(f"Unsupported manual test file suffix: {path.suffix}")

    return Attachment(
        filename=path.name,
        media_type=media_type,
        content=path.read_bytes(),
    )


if __name__ == "__main__":
    raise SystemExit(main())
