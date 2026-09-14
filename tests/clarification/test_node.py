"""Tests for the clarification LangGraph node."""

import pytest
from contextlib import contextmanager
from langchain_core.messages import AIMessage

from app.clarification.node import ask_for_clarification
from app.clarification.schemas import (
    ClarificationInput,
    ClarificationReasonCode,
    ClarificationResult,
)
from app.contracts.intent_decision import IntentDecision, IntentType
from app.clarification import node as clarification_node_module


class FakeClarificationGenerator:
    def __init__(self, result: ClarificationResult):
        self.result = result
        self.input_data: ClarificationInput | None = None

    def generate(self, input_data: ClarificationInput) -> ClarificationResult:
        self.input_data = input_data
        return self.result


def _ambiguous_decision(query: str = "Help with this certificate") -> IntentDecision:
    return IntentDecision(
        query=query,
        intent_type=IntentType.AMBIGUOUS,
        confidence_score=0.42,
    )


def _generator(question: str = "Which state are you applying in?"):
    return FakeClarificationGenerator(
        ClarificationResult(
            question=question,
            reason_code=ClarificationReasonCode.MISSING_LOCATION,
            missing_dimensions=["location"],
        )
    )


def test_node_requires_intent_decision() -> None:
    with pytest.raises(ValueError, match="intent_decision is required"):
        ask_for_clarification({}, _generator())


def test_node_requires_ambiguous_intent() -> None:
    decision = IntentDecision(
        query="PAN application steps",
        intent_type=IntentType.DOCUMENT_INFO,
        confidence_score=0.9,
    )

    with pytest.raises(ValueError, match="requires ambiguous intent"):
        ask_for_clarification({"intent_decision": decision}, _generator())


def test_node_emits_one_assistant_message_and_increments_round_count() -> None:
    generator = _generator("Which state are you applying in?")

    result = ask_for_clarification(
        {
            "intent_decision": _ambiguous_decision(),
            "messages": [{"role": "human", "content": "Need certificate help"}],
            "conversation_summary": "Earlier discussion about certificates.",
            "clarification_round_count": 1,
        },
        generator,
    )

    assert list(result) == ["messages", "clarification_round_count"]
    assert result["clarification_round_count"] == 2
    assert len(result["messages"]) == 1
    assert isinstance(result["messages"][0], AIMessage)
    assert result["messages"][0].content == "Which state are you applying in?"


def test_node_passes_query_messages_summary_and_round_count_to_generator() -> None:
    messages = [{"role": "human", "content": "Earlier turn"}]
    generator = _generator()

    ask_for_clarification(
        {
            "intent_decision": _ambiguous_decision("Classifier-facing request"),
            "messages": messages,
            "conversation_summary": "Older context",
            "clarification_round_count": 2,
        },
        generator,
    )

    assert generator.input_data is not None
    assert generator.input_data.intent_type == IntentType.AMBIGUOUS
    assert generator.input_data.classification_query == "Classifier-facing request"
    assert generator.input_data.messages == messages
    assert generator.input_data.conversation_summary == "Older context"
    assert generator.input_data.clarification_round_count == 2


def test_node_does_not_require_normalized_input() -> None:
    result = ask_for_clarification(
        {"intent_decision": _ambiguous_decision()},
        _generator(),
    )

    assert result["clarification_round_count"] == 1
    assert isinstance(result["messages"][0], AIMessage)


def test_round_count_increments_only_after_generator_succeeds() -> None:
    class FailingGenerator:
        def generate(self, input_data: ClarificationInput) -> ClarificationResult:
            raise RuntimeError("provider failed")

    with pytest.raises(RuntimeError, match="provider failed"):
        ask_for_clarification(
            {
                "intent_decision": _ambiguous_decision(),
                "clarification_round_count": 2,
            },
            FailingGenerator(),
        )


def test_langfuse_update_failure_does_not_fail_node(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingObservation:
        def update(self, **kwargs: object) -> None:
            raise RuntimeError("langfuse update failed")

    @contextmanager
    def fake_start_observation(*args: object, **kwargs: object):
        yield FailingObservation()

    monkeypatch.setattr(
        clarification_node_module,
        "start_observation",
        fake_start_observation,
    )

    result = ask_for_clarification(
        {"intent_decision": _ambiguous_decision()},
        _generator("Which document do you mean?"),
    )

    assert result["messages"][0].content == "Which document do you mean?"
    assert result["clarification_round_count"] == 1
