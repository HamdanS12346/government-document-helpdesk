"""LangGraph node orchestration for intent classification."""

from typing import Any

from langchain_community.callbacks import get_openai_callback

from app.contracts.intent_decision import IntentDecision
from app.contracts.normalized_input import NormalizedInput
from app.graph.state import State
from app.intent.classifier import IntentClassifier
from app.intent.query_builder import build_classification_query
from app.observability import start_observation
from app.observability.metadata import (
    build_intent_decision_metadata,
    build_normalized_input_metadata,
)


def classify_intent(state: State, classifier: IntentClassifier) -> dict[str, IntentDecision]:
    """Classify the current request and return its state update."""

    normalized_input = state.get("normalized_input")
    if normalized_input is None:
        raise ValueError("normalized_input is required for intent classification")
    if not isinstance(normalized_input, NormalizedInput):
        normalized_input = NormalizedInput.model_validate(normalized_input)

    messages = state.get("messages", [])
    conversation_summary = state.get("conversation_summary")
    with start_observation(
        "intent_classifier",
        as_type="generation",
        model="gpt-4o-mini",
        input=build_normalized_input_metadata(
            normalized_input,
            messages=messages,
            conversation_summary=conversation_summary,
        ),
    ) as observation:
        query = build_classification_query(
            normalized_input,
            messages=messages,
            conversation_summary=conversation_summary,
        )
        with get_openai_callback() as cb:
            provider_decision = classifier.classify(query)
        decision = IntentDecision.model_validate(provider_decision)
        decision = decision.model_copy(update={"query": query})
        output_data = build_intent_decision_metadata(decision)
        if cb.total_tokens > 0:
            output_data["token_usage"] = {
                "input_tokens": cb.prompt_tokens,
                "output_tokens": cb.completion_tokens,
                "total_tokens": cb.total_tokens,
            }
        observation.update(
            output=output_data,
            usage_details={
                "input": cb.prompt_tokens,
                "output": cb.completion_tokens,
                "total": cb.total_tokens,
            },
        )
    return {"intent_decision": decision}
