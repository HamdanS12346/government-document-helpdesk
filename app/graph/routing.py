"""Workflow routing helpers."""

from app.contracts.intent_decision import IntentType
from app.graph.graph import (
    CLARIFICATION_NODE,
    GENERAL_CHAT_PLACEHOLDER_NODE,
    RESPONSE_NODE,
    RETRIEVER_NODE,
)
from app.graph.state import State
from app.observability import start_observation


MAX_CLARIFICATION_ROUNDS = 3


def _safe_clarification_round_count(raw_count: object) -> int:
    """Safely parse clarification_round_count against non-int, negative, or corrupt values."""
    if raw_count is None:
        return 0
    try:
        val = int(raw_count)  # type: ignore[arg-type]
        return max(0, val)
    except (ValueError, TypeError):
        return 0


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
        clarification_round_count = _safe_clarification_round_count(
            state.get("clarification_round_count")
        )
        if clarification_round_count >= MAX_CLARIFICATION_ROUNDS:
            selected_node = RETRIEVER_NODE
        else:
            selected_node = CLARIFICATION_NODE
    else:
        raise ValueError(f"unsupported intent_type: {intent_type}")

    safe_count = _safe_clarification_round_count(state.get("clarification_round_count"))
    with start_observation(
        "route_after_intent",
        input={
            "intent_type": str(intent_type),
            "confidence_score": decision.confidence_score,
            "clarification_round_count": safe_count,
            "max_clarification_rounds": MAX_CLARIFICATION_ROUNDS,
        },
    ) as observation:
        observation.update(
            output={
                "selected_node": selected_node,
                "selected_path": str(intent_type),
                "clarification_limit_forced_retriever": (
                    intent_type == IntentType.AMBIGUOUS
                    and selected_node == RETRIEVER_NODE
                ),
            }
        )
    return selected_node


def route_after_intent_full(state: State) -> str:
    """Route to the next graph node after intent classification.

    Used by build_full_graph — general_chat goes directly to the Response Node,
    document_info routes to retriever, and ambiguous routes to the Clarification Node
    (or retriever if max clarification rounds are reached).
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
        clarification_round_count = _safe_clarification_round_count(
            state.get("clarification_round_count")
        )
        if clarification_round_count >= MAX_CLARIFICATION_ROUNDS:
            selected_node = RETRIEVER_NODE
        else:
            selected_node = CLARIFICATION_NODE
    else:
        raise ValueError(f"unsupported intent_type: {intent_type}")

    safe_count = _safe_clarification_round_count(state.get("clarification_round_count"))
    with start_observation(
        "route_after_intent_full",
        input={
            "intent_type": str(intent_type),
            "confidence_score": decision.confidence_score,
            "clarification_round_count": safe_count,
            "max_clarification_rounds": MAX_CLARIFICATION_ROUNDS,
        },
    ) as observation:
        observation.update(
            output={
                "selected_node": selected_node,
                "selected_path": str(intent_type),
                "clarification_limit_forced_retriever": (
                    intent_type == IntentType.AMBIGUOUS
                    and selected_node == RETRIEVER_NODE
                ),
            }
        )
    return selected_node




__all__ = ["MAX_CLARIFICATION_ROUNDS", "route_after_intent","route_after_intent_full"]
