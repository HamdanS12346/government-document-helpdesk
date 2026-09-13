"""LangGraph node orchestration for intent classification."""

from typing import Any

from app.contracts.intent_decision import IntentDecision
from app.contracts.normalized_input import NormalizedInput
from app.graph.state import State
from app.intent.classifier import IntentClassifier
from app.intent.query_builder import build_classification_query


def classify_intent(state: State, classifier: IntentClassifier) -> dict[str, IntentDecision]:
    """Classify the current request and return its state update."""

    normalized_input = state.get("normalized_input")
    if normalized_input is None:
        raise ValueError("normalized_input is required for intent classification")
    if not isinstance(normalized_input, NormalizedInput):
        normalized_input = NormalizedInput.model_validate(normalized_input)

    query = build_classification_query(
        normalized_input,
        messages=state.get("messages", []),
        conversation_summary=state.get("conversation_summary"),
    )
    provider_decision = classifier.classify(query)
    decision = IntentDecision.model_validate(provider_decision)
    decision = decision.model_copy(update={"query": query})
    return {"intent_decision": decision}
