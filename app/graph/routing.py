"""Workflow routing helpers."""

from app.contracts.intent_decision import IntentType
from app.graph.graph import (
    CLARIFICATION_PLACEHOLDER_NODE,
    GENERAL_CHAT_PLACEHOLDER_NODE,
    RESPONSE_NODE,
    RETRIEVER_NODE,
)
from app.graph.state import State
from app.observability import start_observation


def route_after_intent(state: State) -> str:
    """Route to the next graph node after intent classification.

    Used by build_intent_retriever_graph (legacy — placeholders still active).
    """

    decision = state.get("intent_decision")
    if decision is None:
        raise ValueError("intent_decision is required for intent routing")

    intent_type = decision.intent_type

    if intent_type == IntentType.DOCUMENT_INFO:
        selected_node = RETRIEVER_NODE
    elif intent_type == IntentType.GENERAL_CHAT:
        selected_node = GENERAL_CHAT_PLACEHOLDER_NODE
    elif intent_type == IntentType.AMBIGUOUS:
        selected_node = CLARIFICATION_PLACEHOLDER_NODE
    else:
        raise ValueError(f"unsupported intent_type: {intent_type}")

    with start_observation(
        "route_after_intent",
        input={
            "intent_type": str(intent_type),
            "confidence_score": decision.confidence_score,
        },
    ) as observation:
        observation.update(
            output={
                "selected_node": selected_node,
                "selected_path": str(intent_type),
            }
        )
    return selected_node


def route_after_intent_full(state: State) -> str:
    """Route to the next graph node after intent classification.

    Used by build_full_graph — general_chat goes directly to the real Response Node.
    Clarification remains on a placeholder until that node is implemented.
    """

    decision = state.get("intent_decision")
    if decision is None:
        raise ValueError("intent_decision is required for intent routing")

    intent_type = decision.intent_type

    if intent_type == IntentType.DOCUMENT_INFO:
        selected_node = RETRIEVER_NODE
    elif intent_type == IntentType.GENERAL_CHAT:
        selected_node = RESPONSE_NODE
    elif intent_type == IntentType.AMBIGUOUS:
        selected_node = CLARIFICATION_PLACEHOLDER_NODE
    else:
        raise ValueError(f"unsupported intent_type: {intent_type}")

    with start_observation(
        "route_after_intent_full",
        input={
            "intent_type": str(intent_type),
            "confidence_score": decision.confidence_score,
        },
    ) as observation:
        observation.update(
            output={
                "selected_node": selected_node,
                "selected_path": str(intent_type),
            }
        )
    return selected_node


__all__ = ["route_after_intent", "route_after_intent_full"]

