"""LangGraph assembly entry points."""

from collections.abc import Callable, Iterable
from typing import Any
import uuid

from langchain_core.messages import HumanMessage
from langgraph.graph import END, START, StateGraph

from app.clarification.node import clarification_node
from app.graph.state import State
from app.input_processing.processors import build_graph_state_update
from app.input_processing.schemas import InputProcessingResult
from app.intent.classifier import IntentClassifier
from app.intent.node import classify_intent
from app.observability import start_observation
from app.rag.context_builder.node import context_builder_node
from app.rag.node import retriever_node
from app.response.guardrail_node import response_guardrail_node
from app.response.node import response_node


INTENT_CLASSIFIER_NODE = "intent_classifier"
RETRIEVER_NODE = "retriever"
CONTEXT_BUILDER_NODE = "context_builder"
RESPONSE_NODE = "response"
RESPONSE_GUARDRAIL_NODE = "response_guardrail"
GENERAL_CHAT_PLACEHOLDER_NODE = "general_chat_placeholder"
CLARIFICATION_NODE = "clarification"


def general_chat_placeholder(state: State) -> dict[str, Any]:
    """Placeholder branch until the Response Node is implemented."""

    with start_observation(
        GENERAL_CHAT_PLACEHOLDER_NODE,
        input={"status": "placeholder"},
    ) as observation:
        observation.update(output={"status": "general_chat_placeholder"})
    return {"clarification_round_count": 0}


def _run_retriever_and_reset_clarification(
    state: State,
    retriever: Callable[[State], dict[str, Any]],
) -> dict[str, Any]:
    """Run retriever and reset the active clarification counter."""

    update = dict(retriever(state))
    update["clarification_round_count"] = 0
    return update


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
    clarification: Callable[[State], dict[str, Any]] = clarification_node,
) -> Any:
    """Build the graph slice from normalized input through retrieved context."""

    from app.graph.routing import route_after_intent

    graph = StateGraph(State)
    graph.add_node(
        INTENT_CLASSIFIER_NODE,
        lambda state: classify_intent(state, classifier),
    )
    graph.add_node(
        RETRIEVER_NODE,
        lambda state: _run_retriever_and_reset_clarification(state, retriever),
    )
    graph.add_node(CONTEXT_BUILDER_NODE, context_builder)
    graph.add_node(GENERAL_CHAT_PLACEHOLDER_NODE, general_chat_placeholder)
    graph.add_node(CLARIFICATION_NODE, clarification)

    graph.add_edge(START, INTENT_CLASSIFIER_NODE)
    graph.add_conditional_edges(
        INTENT_CLASSIFIER_NODE,
        route_after_intent,
        {
            RETRIEVER_NODE: RETRIEVER_NODE,
            GENERAL_CHAT_PLACEHOLDER_NODE: GENERAL_CHAT_PLACEHOLDER_NODE,
            CLARIFICATION_NODE: CLARIFICATION_NODE,
        },
    )
    graph.add_edge(RETRIEVER_NODE, CONTEXT_BUILDER_NODE)
    graph.add_edge(CONTEXT_BUILDER_NODE, END)
    graph.add_edge(GENERAL_CHAT_PLACEHOLDER_NODE, END)
    graph.add_edge(CLARIFICATION_NODE, END)
    return graph.compile()


def build_full_graph(
    classifier: IntentClassifier,
    retriever: Callable[[State], dict[str, Any]] = retriever_node,
    context_builder: Callable[[State], dict[str, Any]] = context_builder_node,
    responder: Callable[[State], dict[str, Any]] = response_node,
    clarification: Callable[[State], dict[str, Any]] = clarification_node,
) -> Any:
    """Build the complete graph: Intent → [Retriever → Context Builder →] Response.

    Both document_info and general_chat paths converge at the Response Node.
    The clarification path routes to the Clarification Node.
    """

    from app.graph.routing import route_after_intent_full

    graph = StateGraph(State)
    graph.add_node(
        INTENT_CLASSIFIER_NODE,
        lambda state: classify_intent(state, classifier),
    )
    graph.add_node(
        RETRIEVER_NODE,
        lambda state: _run_retriever_and_reset_clarification(state, retriever),
    )
    graph.add_node(CONTEXT_BUILDER_NODE, context_builder)
    graph.add_node(RESPONSE_NODE, responder)
    graph.add_node(CLARIFICATION_NODE, clarification)

    graph.add_edge(START, INTENT_CLASSIFIER_NODE)
    graph.add_conditional_edges(
        INTENT_CLASSIFIER_NODE,
        route_after_intent_full,
        {
            RETRIEVER_NODE: RETRIEVER_NODE,
            RESPONSE_NODE: RESPONSE_NODE,
            CLARIFICATION_NODE: CLARIFICATION_NODE,
        },
    )
    graph.add_edge(RETRIEVER_NODE, CONTEXT_BUILDER_NODE)
    graph.add_edge(CONTEXT_BUILDER_NODE, RESPONSE_NODE)
    graph.add_node(RESPONSE_GUARDRAIL_NODE, response_guardrail_node)
    graph.add_edge(RESPONSE_NODE, RESPONSE_GUARDRAIL_NODE)
    graph.add_edge(CLARIFICATION_NODE, RESPONSE_GUARDRAIL_NODE)
    graph.add_edge(RESPONSE_GUARDRAIL_NODE, END)
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
    clarification: Callable[[State], dict[str, Any]] = clarification_node,
    *,
    thread_id: str | None = None,
    messages: Iterable[Any] | None = None,
    conversation_summary: str | None = None,
    clarification_round_count: int | None = None,
) -> State:
    """Run intent classification and build context for document-info requests."""

    state = build_graph_state_update(result)
    if "normalized_input" not in state:
        raise ValueError("successful normalized_input is required to run the graph")

    if thread_id is not None:
        state["thread_id"] = thread_id
    if messages is not None:
        state["messages"] = list(messages)
    if conversation_summary is not None:
        state["conversation_summary"] = conversation_summary
    if clarification_round_count is not None:
        state["clarification_round_count"] = clarification_round_count

    graph = build_intent_retriever_graph(
        classifier,
        retriever,
        context_builder,
        clarification,
    )
    return graph.invoke(state)


def invoke_full_graph(
    result: InputProcessingResult,
    classifier: IntentClassifier,
    retriever: Callable[[State], dict[str, Any]] = retriever_node,
    context_builder: Callable[[State], dict[str, Any]] = context_builder_node,
    responder: Callable[[State], dict[str, Any]] = response_node,
    clarification: Callable[[State], dict[str, Any]] = clarification_node,
    *,
    thread_id: str | None = None,
    memory_manager: Any | None = None,
    messages: Iterable[Any] | None = None,
    conversation_summary: str | None = None,
    clarification_round_count: int | None = None,
    user_id: str | None = None,
) -> State:
    """Run the complete graph from input processing through response generation.

    If memory_manager is provided, it automatically loads the active working window
    and current conversation summary from memory before graph execution, and persists
    the resulting turn pair (with threshold windowing and rolling summarization) upon completion.
    """

    state = build_graph_state_update(result)
    if "normalized_input" not in state:
        raise ValueError("successful normalized_input is required to run the graph")

    active_thread_id = thread_id or (str(uuid.uuid4()) if memory_manager is not None else None)
    if active_thread_id is not None:
        state["thread_id"] = active_thread_id
    if user_id is not None:
        state["user_id"] = user_id

    if memory_manager is not None and active_thread_id is not None:
        try:
            loaded = memory_manager.load_memory(state=state, thread_id=active_thread_id)
        except TypeError:
            loaded = memory_manager.load_memory(active_thread_id)

        if isinstance(loaded, dict):
            if loaded.get("messages"):
                state["messages"] = list(loaded["messages"])
            if loaded.get("conversation_summary"):
                state["conversation_summary"] = loaded["conversation_summary"]
        elif hasattr(loaded, "messages"):
            state["messages"] = list(loaded.messages)
            if getattr(loaded, "summary", None):
                state["conversation_summary"] = loaded.summary

    if messages is not None:
        state["messages"] = list(messages)
    if conversation_summary is not None:
        state["conversation_summary"] = conversation_summary
    if clarification_round_count is not None:
        state["clarification_round_count"] = clarification_round_count

    graph = build_full_graph(
        classifier,
        retriever,
        context_builder,
        responder,
        clarification,
    )
    output_state = graph.invoke(state)

    if memory_manager is not None and active_thread_id is not None:
        output_messages = output_state.get("messages")
        if output_messages:
            human_text = result.normalized_input.user_query
            ai_message = output_messages[-1]
            try:
                saved = memory_manager.save_turn(
                    state=output_state,
                    thread_id=active_thread_id,
                    user_id=user_id,
                )
            except (TypeError, AttributeError):
                saved = memory_manager.save_turn(
                    thread_id=active_thread_id,
                    human_message=HumanMessage(content=human_text),
                    ai_message=ai_message,
                )
            if isinstance(saved, dict):
                if "messages" in saved:
                    output_state["messages"] = saved["messages"]
                if "conversation_summary" in saved:
                    output_state["conversation_summary"] = saved["conversation_summary"]

    if active_thread_id is not None:
        output_state["thread_id"] = active_thread_id
    if user_id is not None:
        output_state["user_id"] = user_id

    return output_state


__all__ = [
    "CLARIFICATION_NODE",
    "CONTEXT_BUILDER_NODE",
    "GENERAL_CHAT_PLACEHOLDER_NODE",
    "INTENT_CLASSIFIER_NODE",
    "RESPONSE_GUARDRAIL_NODE",
    "RESPONSE_NODE",
    "RETRIEVER_NODE",
    "build_full_graph",
    "build_input_intent_graph",
    "build_intent_retriever_graph",
    "general_chat_placeholder",
    "invoke_full_graph",
    "invoke_input_intent_graph",
    "invoke_intent_retriever_graph",
]
