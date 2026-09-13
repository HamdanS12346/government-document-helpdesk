"""Intent decision contract definitions."""

from pydantic import BaseModel, Field


class IntentDecision(BaseModel):
    """Intent classification result."""

    query: str = Field(description="Query evaluated for classification")
    intent_type: str = Field(description="Detected intent type: document_info, general_chat, or ambiguous")
    confidence_score: float = Field(ge=0.0, le=1.0, description="Confidence score between 0.0 and 1.0")


__all__ = ["IntentDecision"]
