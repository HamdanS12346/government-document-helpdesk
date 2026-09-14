"""Internal schemas for the Clarification Node."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.contracts.intent_decision import IntentType


class ClarificationReasonCode(StrEnum):
    """Supported local reason codes for clarification questions."""

    MISSING_DOCUMENT_TYPE = "missing_document_type"
    MISSING_SERVICE_OR_TASK = "missing_service_or_task"
    MISSING_LOCATION = "missing_location"
    MISSING_APPLICANT_CONTEXT = "missing_applicant_context"
    MISSING_ATTACHMENT_REFERENCE = "missing_attachment_reference"
    UNCLEAR_REQUEST = "unclear_request"


class ClarificationInput(BaseModel):
    """Validated input assembled for clarification generation."""

    intent_type: IntentType
    classification_query: str = Field(min_length=1)
    messages: list[Any] = Field(default_factory=list)
    conversation_summary: str | None = None
    clarification_round_count: int = Field(default=0, ge=0)

    @field_validator("classification_query")
    @classmethod
    def classification_query_must_not_be_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("classification_query must not be blank")
        return cleaned

    @field_validator("conversation_summary")
    @classmethod
    def empty_summary_becomes_none(cls, value: str | None) -> str | None:
        if value is None:
            return None

        cleaned = value.strip()
        return cleaned or None


class ClarificationResult(BaseModel):
    """Structured result returned by a clarification generator."""

    question: str = Field(min_length=1)
    reason_code: ClarificationReasonCode
    missing_dimensions: list[str] = Field(default_factory=list)

    @field_validator("question")
    @classmethod
    def question_must_not_be_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("question must not be blank")
        return cleaned

    @field_validator("missing_dimensions")
    @classmethod
    def missing_dimensions_must_not_be_blank(cls, values: list[str]) -> list[str]:
        cleaned_values = [value.strip() for value in values if value.strip()]
        if len(cleaned_values) != len(values):
            raise ValueError("missing_dimensions must not contain blank values")
        return cleaned_values
