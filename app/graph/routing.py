"""Workflow routing helpers."""

from app.contracts.intent_decision import IntentType
from app.graph.graph import (
    CLARIFICATION_PLACEHOLDER_NODE,
    GENERAL_CHAT_PLACEHOLDER_NODE,
    RETRIEVER_NODE,
)
from app.graph.state import State


def route_after_intent(state: State) -> str:
    """Route to the next graph node after intent classification."""

    decision = state.get("intent_decision")
    if decision is None:
        raise ValueError("intent_decision is required for intent routing")

    intent_type = decision.intent_type

    if intent_type == IntentType.DOCUMENT_INFO:
        return RETRIEVER_NODE
    if intent_type == IntentType.GENERAL_CHAT:
        return GENERAL_CHAT_PLACEHOLDER_NODE
    if intent_type == IntentType.AMBIGUOUS:
        return CLARIFICATION_PLACEHOLDER_NODE

    raise ValueError(f"unsupported intent_type: {intent_type}")


__all__ = ["route_after_intent"]
