"""Development CLI for the public Input Processor boundary."""

import argparse
import mimetypes
from pathlib import Path
from typing import Sequence

from app.input_processing.processors import process_input
from app.input_processing.schemas import Attachment, InputRequest


PREVIEW_DISPLAY_LIMIT = 120


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="input-processor",
        description="Process text and file inputs through the Input Processor.",
    )
    parser.add_argument(
        "--text",
        default=None,
        help="Optional user text to process with attachments.",
    )
    parser.add_argument(
        "--file",
        action="append",
        default=[],
        help="Attachment file path. May be provided more than once.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        request = InputRequest(
            user_query=args.text,
            attachments=[_attachment_from_path(Path(path)) for path in args.file],
        )
    except Exception:
        print("Input Processor: failed")
        print("Error: request could not be constructed safely.")
        return 2

    result = process_input(request)
    if not result.success:
        print("Input Processor: failed")
        _print_attachment_statuses(result.attachment_statuses)
        return 1

    print("Input Processor: success")
    assert result.normalized_input is not None
    print(f"Images processed: {len(result.normalized_input.image_content)}")
    print(f"PDFs processed: {len(result.normalized_input.pdf_content)}")
    if result.normalized_input.user_query:
        print(f"User text: {_preview(result.normalized_input.user_query)}")

    for image_content in result.normalized_input.image_content:
        print(f"Image {image_content.image_name}: {_preview(image_content.preview)}")
    for pdf_content in result.normalized_input.pdf_content:
        print(f"PDF {pdf_content.pdf_name}: {_preview(pdf_content.preview)}")

    _print_attachment_statuses(result.attachment_statuses)
    return 0


def _attachment_from_path(path: Path) -> Attachment:
    media_type, _ = mimetypes.guess_type(path.name)
    return Attachment(
        filename=path.name,
        media_type=media_type or "application/octet-stream",
        content=path.read_bytes(),
    )


def _print_attachment_statuses(statuses) -> None:
    for status in statuses:
        if status.status == "success":
            print(f"{status.filename}: success")
            continue
        if status.error is None:
            print(f"{status.filename}: failed")
            continue
        print(f"{status.filename}: failed ({status.error.code}) {status.error.message}")


def _preview(text: str) -> str:
    normalized = " ".join(text.split())
    return normalized[:PREVIEW_DISPLAY_LIMIT]


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["PREVIEW_DISPLAY_LIMIT", "build_parser", "main"]
