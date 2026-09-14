"""Tests for clarification-local schemas."""

import pytest
from pydantic import ValidationError

from app.clarification.schemas import (
    ClarificationInput,
    ClarificationReasonCode,
    ClarificationResult,
)
from app.contracts.intent_decision import IntentType


def test_clarification_input_accepts_placeholder_conversation_context() -> None:
    model = ClarificationInput(
        intent_type=IntentType.AMBIGUOUS,
        classification_query="  Help with my uploaded certificate  ",
        messages=[{"role": "human", "content": "I uploaded a file."}],
        conversation_summary="  Earlier PAN discussion.  ",
        clarification_round_count=1,
    )

    assert model.classification_query == "Help with my uploaded certificate"
    assert model.messages == [{"role": "human", "content": "I uploaded a file."}]
    assert model.conversation_summary == "Earlier PAN discussion."
    assert model.clarification_round_count == 1


def test_clarification_input_rejects_blank_classification_query() -> None:
    with pytest.raises(ValidationError):
        ClarificationInput(
            intent_type=IntentType.AMBIGUOUS,
            classification_query="   ",
        )


def test_clarification_input_rejects_negative_round_count() -> None:
    with pytest.raises(ValidationError):
        ClarificationInput(
            intent_type=IntentType.AMBIGUOUS,
            classification_query="Which certificate?",
            clarification_round_count=-1,
        )


def test_clarification_result_accepts_valid_reason_code() -> None:
    result = ClarificationResult(
        question="Which state are you applying in?",
        reason_code=ClarificationReasonCode.MISSING_LOCATION,
        missing_dimensions=["location"],
    )

    assert result.reason_code == ClarificationReasonCode.MISSING_LOCATION
    assert result.missing_dimensions == ["location"]


def test_clarification_result_rejects_empty_question() -> None:
    with pytest.raises(ValidationError):
        ClarificationResult(
            question="   ",
            reason_code=ClarificationReasonCode.UNCLEAR_REQUEST,
            missing_dimensions=["request"],
        )


def test_clarification_result_rejects_invalid_reason_code() -> None:
    with pytest.raises(ValidationError):
        ClarificationResult(
            question="Which document do you mean?",
            reason_code="unsupported_reason",
            missing_dimensions=["document_type"],
        )


def test_clarification_result_rejects_blank_missing_dimension() -> None:
    with pytest.raises(ValidationError):
        ClarificationResult(
            question="Which document do you mean?",
            reason_code=ClarificationReasonCode.MISSING_DOCUMENT_TYPE,
            missing_dimensions=["document_type", " "],
        )
