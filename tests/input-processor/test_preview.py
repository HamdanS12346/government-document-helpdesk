"""Deterministic preview helper tests for the Input Processor."""

from app.input_processing.preview import (
    IMAGE_PREVIEW_CHARACTER_LIMIT,
    PDF_PREVIEW_CHARACTERS_PER_PAGE,
    build_image_preview,
    build_pdf_preview,
)


def test_build_image_preview_returns_short_text_unchanged() -> None:
    assert build_image_preview("short extracted text") == "short extracted text"


def test_build_image_preview_limits_to_first_500_characters() -> None:
    extracted_text = "a" * (IMAGE_PREVIEW_CHARACTER_LIMIT + 1)

    preview = build_image_preview(extracted_text)

    assert preview == "a" * IMAGE_PREVIEW_CHARACTER_LIMIT


def test_build_pdf_preview_returns_page_aware_preview() -> None:
    page_texts = [
        "page one text",
        "page two text",
    ]

    assert build_pdf_preview(page_texts) == "page one text\npage two text"


def test_build_pdf_preview_limits_each_page_to_200_characters() -> None:
    page_texts = [
        "a" * (PDF_PREVIEW_CHARACTERS_PER_PAGE + 10),
        "b" * (PDF_PREVIEW_CHARACTERS_PER_PAGE + 20),
    ]

    preview = build_pdf_preview(page_texts)

    assert preview == (
        ("a" * PDF_PREVIEW_CHARACTERS_PER_PAGE)
        + "\n"
        + ("b" * PDF_PREVIEW_CHARACTERS_PER_PAGE)
    )


def test_build_pdf_preview_handles_empty_page_list() -> None:
    assert build_pdf_preview([]) == ""
