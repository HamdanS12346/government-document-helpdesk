"""Shared graph state definitions."""

from typing import Any, NotRequired, TypedDict

from app.contracts.intent_decision import IntentDecision
from app.contracts.normalized_input import NormalizedInput


class GraphState(TypedDict, total=False):
    """Shared LangGraph state passed between workflow nodes.

    Raw uploads, upload objects, temporary paths, OCR providers, and internal
    input-processing results must stay outside this shared state.
    """

    normalized_input: NotRequired[NormalizedInput]
    intent_decision: NotRequired[IntentDecision]
    documents: NotRequired[list[Any]]
    retrieved_context: NotRequired[Any]
    messages: NotRequired[list[Any]]
    conversation_summary: NotRequired[str]
    clarification_round_count: NotRequired[int]


State = GraphState

__all__ = ["GraphState", "State"]
