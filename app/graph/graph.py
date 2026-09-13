"""LangGraph assembly entry points."""

from collections.abc import Iterable
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.graph.state import State
from app.input_processing.processors import build_graph_state_update
from app.input_processing.schemas import InputProcessingResult
from app.intent.classifier import IntentClassifier
from app.intent.node import classify_intent


INTENT_CLASSIFIER_NODE = "intent_classifier"


def build_input_intent_graph(classifier: IntentClassifier) -> Any:
    """Build the current graph slice from normalized input to intent decision."""

    graph = StateGraph(State)
    graph.add_node(
        INTENT_CLASSIFIER_NODE,
        lambda state: classify_intent(state, classifier),
    )
    graph.add_edge(START, INTENT_CLASSIFIER_NODE)
    graph.add_edge(INTENT_CLASSIFIER_NODE, END)
    return graph.compile()


def invoke_input_intent_graph(
    result: InputProcessingResult,
    classifier: IntentClassifier,
    *,
    messages: Iterable[Any] | None = None,
    conversation_summary: str | None = None,
) -> State:
    """Run intent classification from a successful Input Processor result."""

    state = build_graph_state_update(result)
    if "normalized_input" not in state:
        raise ValueError("successful normalized_input is required to run the graph")

    if messages is not None:
        state["messages"] = list(messages)
    if conversation_summary is not None:
        state["conversation_summary"] = conversation_summary

    graph = build_input_intent_graph(classifier)
    return graph.invoke(state)


__all__ = [
    "INTENT_CLASSIFIER_NODE",
    "build_input_intent_graph",
    "invoke_input_intent_graph",
]
