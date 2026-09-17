"""Synthetic spreadsheet fixture helpers for Input Processor tests."""

from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile


def make_minimal_xlsx_package_bytes() -> bytes:
    """Return minimal OOXML workbook bytes for validation-boundary tests."""

    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types></Types>")
        archive.writestr("xl/workbook.xml", "<workbook></workbook>")
    return buffer.getvalue()


def make_incomplete_xlsx_package_bytes() -> bytes:
    """Return OOXML-like bytes missing required workbook parts."""

    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types></Types>")
    return buffer.getvalue()


def make_corrupt_zip_like_xlsx_bytes() -> bytes:
    """Return bytes with a ZIP signature but invalid archive structure."""

    return b"PK\x03\x04not a valid zip package"


__all__ = [
    "make_corrupt_zip_like_xlsx_bytes",
    "make_incomplete_xlsx_package_bytes",
    "make_minimal_xlsx_package_bytes",
]
