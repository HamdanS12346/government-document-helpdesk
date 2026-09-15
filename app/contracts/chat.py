"""Public chat API response contracts."""

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ChatStatus(StrEnum):
    """Stable workflow outcome statuses returned by the chat API."""

    COMPLETED = "completed"
    CLARIFICATION_REQUIRED = "clarification_required"
    INPUT_FAILED = "input_failed"
    CLASSIFICATION_ERROR = "classification_error"
    SYSTEM_ERROR = "system_error"


class ChatMessage(BaseModel):
    """Public assistant/user message representation for transport."""

    model_config = ConfigDict(extra="forbid")

    role: Literal["assistant", "user"]
    content: str


class ChatIntentSummary(BaseModel):
    """Safe, public summary of the graph intent decision."""

    model_config = ConfigDict(extra="forbid")

    type: str
    confidence_score: float | None = Field(default=None, ge=0.0, le=1.0)


class ChatResponse(BaseModel):
    """Stable response shape for the /chat endpoint."""

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    success: bool
    status: ChatStatus
    message: str
    assistant_message: ChatMessage | None = None
    attachment_statuses: list[Any] = Field(default_factory=list)
    warnings: list[Any] = Field(default_factory=list)
    normalized_input: Any | None = None
    intent: ChatIntentSummary | None = None
    conversation_id: str | None = None


__all__ = [
    "ChatIntentSummary",
    "ChatMessage",
    "ChatResponse",
    "ChatStatus",
]
