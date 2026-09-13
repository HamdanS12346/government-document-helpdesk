"""LangGraph assembly entry points."""

from collections.abc import Callable, Iterable
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.graph.state import State
from app.input_processing.processors import build_graph_state_update
from app.input_processing.schemas import InputProcessingResult
from app.intent.classifier import IntentClassifier
from app.intent.node import classify_intent
from app.rag.context_builder.node import context_builder_node
from app.rag.node import retriever_node


INTENT_CLASSIFIER_NODE = "intent_classifier"
RETRIEVER_NODE = "retriever"
CONTEXT_BUILDER_NODE = "context_builder"
GENERAL_CHAT_PLACEHOLDER_NODE = "general_chat_placeholder"
CLARIFICATION_PLACEHOLDER_NODE = "clarification_placeholder"


def general_chat_placeholder(state: State) -> dict[str, Any]:
    """Placeholder branch until the Response Node is implemented."""

    return {}


def clarification_placeholder(state: State) -> dict[str, Any]:
    """Placeholder branch until the Clarification Node is implemented."""

    return {}


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


def build_intent_retriever_graph(
    classifier: IntentClassifier,
    retriever: Callable[[State], dict[str, Any]] = retriever_node,
    context_builder: Callable[[State], dict[str, Any]] = context_builder_node,
) -> Any:
    """Build the graph slice from normalized input through retrieved context."""

    from app.graph.routing import route_after_intent

    graph = StateGraph(State)
    graph.add_node(
        INTENT_CLASSIFIER_NODE,
        lambda state: classify_intent(state, classifier),
    )
    graph.add_node(RETRIEVER_NODE, retriever)
    graph.add_node(CONTEXT_BUILDER_NODE, context_builder)
    graph.add_node(GENERAL_CHAT_PLACEHOLDER_NODE, general_chat_placeholder)
    graph.add_node(CLARIFICATION_PLACEHOLDER_NODE, clarification_placeholder)

    graph.add_edge(START, INTENT_CLASSIFIER_NODE)
    graph.add_conditional_edges(
        INTENT_CLASSIFIER_NODE,
        route_after_intent,
        {
            RETRIEVER_NODE: RETRIEVER_NODE,
            GENERAL_CHAT_PLACEHOLDER_NODE: GENERAL_CHAT_PLACEHOLDER_NODE,
            CLARIFICATION_PLACEHOLDER_NODE: CLARIFICATION_PLACEHOLDER_NODE,
        },
    )
    graph.add_edge(RETRIEVER_NODE, CONTEXT_BUILDER_NODE)
    graph.add_edge(CONTEXT_BUILDER_NODE, END)
    graph.add_edge(GENERAL_CHAT_PLACEHOLDER_NODE, END)
    graph.add_edge(CLARIFICATION_PLACEHOLDER_NODE, END)
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


def invoke_intent_retriever_graph(
    result: InputProcessingResult,
    classifier: IntentClassifier,
    retriever: Callable[[State], dict[str, Any]] = retriever_node,
    context_builder: Callable[[State], dict[str, Any]] = context_builder_node,
    *,
    messages: Iterable[Any] | None = None,
    conversation_summary: str | None = None,
) -> State:
    """Run intent classification and build context for document-info requests."""

    state = build_graph_state_update(result)
    if "normalized_input" not in state:
        raise ValueError("successful normalized_input is required to run the graph")

    if messages is not None:
        state["messages"] = list(messages)
    if conversation_summary is not None:
        state["conversation_summary"] = conversation_summary

    graph = build_intent_retriever_graph(classifier, retriever, context_builder)
    return graph.invoke(state)


__all__ = [
    "CLARIFICATION_PLACEHOLDER_NODE",
    "CONTEXT_BUILDER_NODE",
    "GENERAL_CHAT_PLACEHOLDER_NODE",
    "INTENT_CLASSIFIER_NODE",
    "RETRIEVER_NODE",
    "build_input_intent_graph",
    "build_intent_retriever_graph",
    "clarification_placeholder",
    "general_chat_placeholder",
    "invoke_input_intent_graph",
    "invoke_intent_retriever_graph",
]
