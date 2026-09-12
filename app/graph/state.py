"""Shared graph state definitions."""

from typing import Any, TypedDict

from app.contracts.intent_decision import IntentDecision
from app.contracts.normalized_input import NormalizedInput


class State(TypedDict, total=False):
	"""Shared state exchanged by LangGraph nodes."""

	normalized_input: NormalizedInput
	intent_decision: IntentDecision
	documents: list[Any]
	retrieved_context: Any
	messages: list[Any]
	conversation_summary: str

