"""Spreadsheet fixture strategy tests."""

from guardrails.input_processor import has_xlsx_signature
from spreadsheet_fixture_helpers import (
    make_corrupt_zip_like_xlsx_bytes,
    make_incomplete_xlsx_package_bytes,
    make_minimal_xlsx_package_bytes,
)


def test_minimal_spreadsheet_fixture_bytes_pass_validation_signature() -> None:
    assert has_xlsx_signature(make_minimal_xlsx_package_bytes()) is True


def test_invalid_spreadsheet_fixture_bytes_fail_validation_signature() -> None:
    assert has_xlsx_signature(make_incomplete_xlsx_package_bytes()) is False
    assert has_xlsx_signature(make_corrupt_zip_like_xlsx_bytes()) is False
