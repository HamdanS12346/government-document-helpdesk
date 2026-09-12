"""Intent decision contract."""

from enum import StrEnum

from pydantic import BaseModel, Field


class IntentType(StrEnum):
	"""Supported workflow intents."""

	DOCUMENT_INFO = "document_info"
	GENERAL_CHAT = "general_chat"
	AMBIGUOUS = "ambiguous"


class IntentDecision(BaseModel):
	"""Validated result produced by the intent classifier."""

	query: str = Field(min_length=1)
	intent_type: IntentType
	confidence_score: float = Field(ge=0.0, le=1.0)

