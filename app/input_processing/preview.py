"""Deterministic preview helpers for normalized attachment content."""

IMAGE_PREVIEW_CHARACTER_LIMIT = 500
PDF_PREVIEW_CHARACTERS_PER_PAGE = 200


def build_image_preview(extracted_text: str) -> str:
    """Return the deterministic preview for extracted image text."""

    return extracted_text[:IMAGE_PREVIEW_CHARACTER_LIMIT]


def build_pdf_preview(page_texts: list[str]) -> str:
    """Return a deterministic page-aware preview for extracted PDF text."""

    page_previews = [
        page_text[:PDF_PREVIEW_CHARACTERS_PER_PAGE] for page_text in page_texts
    ]
    return "\n".join(page_previews)


__all__ = [
    "IMAGE_PREVIEW_CHARACTER_LIMIT",
    "PDF_PREVIEW_CHARACTERS_PER_PAGE",
    "build_image_preview",
    "build_pdf_preview",
]
