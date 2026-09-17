"""Spreadsheet configuration foundation tests."""

import pytest
from pydantic import ValidationError

from app.config import Settings


def test_spreadsheet_settings_expose_mvp_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.spreadsheet_supported_extension == ".xlsx"
    assert settings.spreadsheet_parser_package == "openpyxl"
    assert settings.spreadsheet_max_visible_sheets == 5
    assert settings.spreadsheet_max_rows_per_sheet == 50
    assert settings.spreadsheet_max_columns_per_sheet == 50
    assert settings.spreadsheet_max_text_cell_characters == 5_000
    assert settings.spreadsheet_preview_row_count == 5


def test_spreadsheet_settings_are_injectable_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SPREADSHEET_MAX_VISIBLE_SHEETS", "2")
    monkeypatch.setenv("SPREADSHEET_MAX_ROWS_PER_SHEET", "10")
    monkeypatch.setenv("SPREADSHEET_MAX_COLUMNS_PER_SHEET", "8")
    monkeypatch.setenv("SPREADSHEET_MAX_TEXT_CELL_CHARACTERS", "100")
    monkeypatch.setenv("SPREADSHEET_PREVIEW_ROW_COUNT", "3")

    settings = Settings(_env_file=None)

    assert settings.spreadsheet_max_visible_sheets == 2
    assert settings.spreadsheet_max_rows_per_sheet == 10
    assert settings.spreadsheet_max_columns_per_sheet == 8
    assert settings.spreadsheet_max_text_cell_characters == 100
    assert settings.spreadsheet_preview_row_count == 3


@pytest.mark.parametrize(
    ("env_name", "env_value"),
    [
        ("SPREADSHEET_MAX_VISIBLE_SHEETS", "0"),
        ("SPREADSHEET_MAX_ROWS_PER_SHEET", "0"),
        ("SPREADSHEET_MAX_COLUMNS_PER_SHEET", "0"),
        ("SPREADSHEET_MAX_TEXT_CELL_CHARACTERS", "0"),
        ("SPREADSHEET_PREVIEW_ROW_COUNT", "-1"),
    ],
)
def test_spreadsheet_settings_reject_invalid_limits(
    monkeypatch: pytest.MonkeyPatch,
    env_name: str,
    env_value: str,
) -> None:
    monkeypatch.setenv(env_name, env_value)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)
