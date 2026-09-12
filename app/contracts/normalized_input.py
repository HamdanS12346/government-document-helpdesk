"""Normalized input contract."""

from pydantic import BaseModel, ConfigDict


class ImageContent(BaseModel):
    """Processed content extracted from one uploaded image."""

    model_config = ConfigDict(extra="forbid")

    image_name: str
    extracted_text: str
    preview: str


class PDFContent(BaseModel):
    """Processed content extracted from one uploaded PDF."""

    model_config = ConfigDict(extra="forbid")

    pdf_name: str
    extracted_text: str
    preview: str


class NormalizedInput(BaseModel):
    """Normalized user text and successfully processed attachments."""

    model_config = ConfigDict(extra="forbid")

    user_query: str
    image_content: list[ImageContent]
    pdf_content: list[PDFContent]
    combined_text: str


__all__ = ["ImageContent", "NormalizedInput", "PDFContent"]
