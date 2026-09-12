"""Normalized input contract."""

from typing import Any

from pydantic import BaseModel, Field


class NormalizedInput(BaseModel):
	"""Normalized user input consumed by downstream nodes."""

	user_query: str = Field(min_length=1)
	image_preview: list[Any] = Field(default_factory=list)
	pdf_preview: list[Any] = Field(default_factory=list)
	context: Any | None = None

