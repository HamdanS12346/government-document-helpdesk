r"""Manual upload-size streaming runner.

Run:

    .\.venv\Scripts\python.exe test.py
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from app.api.routes import _read_uploaded_files
from app.config import get_settings
from guardrails.input_processor import MAX_ATTACHMENT_SIZE_BYTES


PROJECT_ROOT = Path(__file__).resolve().parent
PDF_PATH = (
    PROJECT_ROOT
    / "tests"
    / "input-processor"
    / "fixtures"
    / "pdfs"
    / "max_file_size"
    / "oversized_test_pdf.pdf"
)
SYNTHETIC_OVERSIZED_SIZE_BYTES = 50 * 1024 * 1024 + 512 * 1024


class TerminalUploadFile:
    """Small UploadFile-compatible wrapper that prints every streamed read."""

    def __init__(
        self,
        path: Path,
        *,
        expose_declared_size: bool,
        filename: str | None = None,
        max_stream_bytes: int | None = None,
    ) -> None:
        self.path = path
        self.filename = filename or path.name
        self.content_type = "application/pdf"
        self.size = (
            max_stream_bytes or path.stat().st_size
            if expose_declared_size
            else None
        )
        self._max_stream_bytes = max_stream_bytes
        self._file = path.open("rb")
        self._read_count = 0
        self._total_returned = 0

    async def read(self, size: int = -1) -> bytes:
        self._read_count += 1
        if (
            self._max_stream_bytes is not None
            and self._total_returned >= self._max_stream_bytes
        ):
            chunk = b""
        else:
            effective_size = size
            if self._max_stream_bytes is not None:
                effective_size = min(
                    size,
                    self._max_stream_bytes - self._total_returned,
                )
            chunk = self._file.read(effective_size)
        self._total_returned += len(chunk)
        print(
            f"{self.filename} chunk {self._read_count:02d}: "
            f"requested={size:,} bytes, returned={len(chunk):,} bytes, "
            f"file_read={self._total_returned:,} bytes"
        )
        return chunk

    def close(self) -> None:
        self._file.close()


async def run_case(
    title: str,
    uploads: list[TerminalUploadFile],
) -> None:
    print(f"\n=== {title} ===")
    print(f"max single file size: {MAX_ATTACHMENT_SIZE_BYTES:,} bytes")
    print(f"max attachment count: {get_settings().upload_max_attachment_count}")
    print(f"max total upload size: {get_settings().upload_max_total_size_bytes:,} bytes")

    try:
        results = await _read_uploaded_files(uploads)
    finally:
        for upload in uploads:
            upload.close()

    for index, result in enumerate(results, start=1):
        print(f"\nresult {index}:")
        if result.error_status is not None:
            error = result.error_status.error
            print("REJECTED")
            print(f"filename: {result.error_status.filename}")
            print(f"status: {result.error_status.status}")
            if error is not None:
                print(f"code: {error.code}")
                print(f"message: {error.message}")
            continue

        if result.file is not None:
            print("ACCEPTED")
            print(f"filename: {result.file.filename}")
            print(f"media_type: {result.file.media_type}")
            print(f"bytes loaded: {len(result.file.content):,}")


def main() -> int:
    print("Manual upload limit test")
    print("This uses the same _read_uploaded_files helper as /chat.")
    if not PDF_PATH.exists():
        print(f"Fixture missing; creating synthetic oversized PDF at: {PDF_PATH}")
        PDF_PATH.parent.mkdir(parents=True, exist_ok=True)
        PDF_PATH.write_bytes(b"%PDF-1.4\n")
        with PDF_PATH.open("ab") as fixture:
            fixture.truncate(SYNTHETIC_OVERSIZED_SIZE_BYTES)
            fixture.write(b"\n%%EOF")

    print(f"fixture: {PDF_PATH}")
    print(f"fixture size: {PDF_PATH.stat().st_size:,} bytes")

    asyncio.run(
        run_case(
            "declared-size per-file precheck",
            [TerminalUploadFile(PDF_PATH, expose_declared_size=True)],
        )
    )
    asyncio.run(
        run_case(
            "streaming per-file size check",
            [TerminalUploadFile(PDF_PATH, expose_declared_size=False)],
        )
    )
    asyncio.run(
        run_case(
            "attachment count precheck",
            [
                TerminalUploadFile(
                    PDF_PATH,
                    expose_declared_size=True,
                    filename=f"file-{index}.pdf",
                )
                for index in range(1, 7)
            ],
        )
    )

    original_total_limit = os.environ.get("UPLOAD_MAX_TOTAL_SIZE_BYTES")
    os.environ["UPLOAD_MAX_TOTAL_SIZE_BYTES"] = str(3 * 1024 * 1024)
    get_settings.cache_clear()
    try:
        asyncio.run(
            run_case(
                "streaming total request size check with temporary 3 MB cap",
                [
                    TerminalUploadFile(
                        PDF_PATH,
                        expose_declared_size=False,
                        filename="first.pdf",
                        max_stream_bytes=2 * 1024 * 1024,
                    ),
                    TerminalUploadFile(
                        PDF_PATH,
                        expose_declared_size=False,
                        filename="second.pdf",
                        max_stream_bytes=2 * 1024 * 1024,
                    ),
                ],
            )
        )
    finally:
        if original_total_limit is None:
            os.environ.pop("UPLOAD_MAX_TOTAL_SIZE_BYTES", None)
        else:
            os.environ["UPLOAD_MAX_TOTAL_SIZE_BYTES"] = original_total_limit
        get_settings.cache_clear()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
