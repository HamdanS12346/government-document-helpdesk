import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.contracts.intent_decision import IntentDecision, IntentType
from app.contracts.normalized_input import NormalizedInput
from app.graph.graph import (
    CLARIFICATION_NODE,
    RESPONSE_NODE,
    RETRIEVER_NODE,
    build_full_graph,
    invoke_full_graph,
)
from app.graph.routing import MAX_CLARIFICATION_ROUNDS, route_after_intent_full
from app.input_processing.schemas import InputProcessingResult


class FakeClassifier:
    def __init__(self, intent_type: IntentType) -> None:
        self.intent_type = intent_type
        self.query = None

    def classify(self, query: str) -> IntentDecision:
        self.query = query
        return IntentDecision(
            query=query,
            intent_type=self.intent_type,
            confidence_score=0.95,
        )


class RecordingRetriever:
    def __init__(self) -> None:
        self.called = False
        self.state = None

    def __call__(self, state: dict) -> dict:
        self.called = True
        self.state = state
        return {
            "documents": [
                {
                    "id": "identity-documents__pan-card__chunk-0001",
                    "text_content": "PAN application requires proof of identity.",
                    "metadata": {
                        "document_id": "identity-documents__pan-card",
                    },
                    "score": 0.91,
                }
            ]
        }


class RecordingContextBuilder:
    def __init__(self) -> None:
        self.called = False
        self.state = None

    def __call__(self, state: dict) -> dict:
        self.called = True
        self.state = state
        return {
            "retrieved_context": {
                "formatted_context": "[Document 1]\nContent:\nPAN application requires proof of identity.",
                "sources": [],
            }
        }


class RecordingResponder:
    def __init__(self, response_text: str = "Test response") -> None:
        self.called = False
        self.state = None
        self.response_text = response_text

    def __call__(self, state: dict) -> dict:
        self.called = True
        self.state = state
        existing_messages = list(state.get("messages", []))
        return {
            "messages": existing_messages + [AIMessage(content=self.response_text)]
        }


class RecordingClarification:
    def __init__(self) -> None:
        self.called = False
        self.state = None

    def __call__(self, state: dict) -> dict:
        self.called = True
        self.state = state
        existing_messages = list(state.get("messages", []))
        return {
            "messages": existing_messages + [AIMessage(content="Which document do you mean?")],
            "clarification_round_count": state.get("clarification_round_count", 0) + 1,
        }


def _normalized_input(query: str = "What documents are needed for PAN application?") -> NormalizedInput:
    return NormalizedInput(
        user_query=query,
        image_content=[],
        pdf_content=[],
        combined_text=query,
    )


def _successful_result(normalized_input: NormalizedInput | None = None) -> InputProcessingResult:
    return InputProcessingResult(
        success=True,
        normalized_input=normalized_input or _normalized_input(),
    )


def _failing_node(name: str):
    def _fn(state: dict) -> dict:
        raise AssertionError(f"Node '{name}' should not have been called!")
    return _fn


def test_build_full_graph_compiles_cleanly():
    """Verify build_full_graph compiles without NameError or schema mismatch."""
    classifier = FakeClassifier(IntentType.DOCUMENT_INFO)
    graph = build_full_graph(
        classifier=classifier,
        retriever=RecordingRetriever(),
        context_builder=RecordingContextBuilder(),
        responder=RecordingResponder(),
        clarification=RecordingClarification(),
    )
    assert graph is not None


def test_document_info_routes_to_retriever_context_builder_response():
    """Document info path executes Retriever -> ContextBuilder -> ResponseNode."""
    classifier = FakeClassifier(IntentType.DOCUMENT_INFO)
    retriever = RecordingRetriever()
    context_builder = RecordingContextBuilder()
    responder = RecordingResponder("Here are the PAN requirements.")
    clarification = _failing_node("clarification")

    result = invoke_full_graph(
        _successful_result(),
        classifier=classifier,
        retriever=retriever,
        context_builder=context_builder,
        responder=responder,
        clarification=clarification,
    )

    assert retriever.called
    assert context_builder.called
    assert responder.called
    assert result["intent_decision"].intent_type == IntentType.DOCUMENT_INFO
    assert len(result["messages"]) == 1
    assert result["messages"][0].content == "Here are the PAN requirements."


def test_general_chat_routes_directly_to_response_node():
    """General chat path bypasses Retriever & ContextBuilder and goes directly to ResponseNode."""
    classifier = FakeClassifier(IntentType.GENERAL_CHAT)
    retriever = _failing_node("retriever")
    context_builder = _failing_node("context_builder")
    responder = RecordingResponder("Hello! How can I assist you with government documents?")
    clarification = _failing_node("clarification")

    result = invoke_full_graph(
        _successful_result(_normalized_input("hello")),
        classifier=classifier,
        retriever=retriever,
        context_builder=context_builder,
        responder=responder,
        clarification=clarification,
    )

    assert responder.called
    assert result["intent_decision"].intent_type == IntentType.GENERAL_CHAT
    assert len(result["messages"]) == 1
    assert result["messages"][0].content == "Hello! How can I assist you with government documents?"


def test_ambiguous_intent_routes_to_clarification_node():
    """Ambiguous intent under threshold routes to Clarification Node."""
    classifier = FakeClassifier(IntentType.AMBIGUOUS)
    retriever = _failing_node("retriever")
    context_builder = _failing_node("context_builder")
    responder = _failing_node("responder")
    clarification = RecordingClarification()

    result = invoke_full_graph(
        _successful_result(_normalized_input("status")),
        classifier=classifier,
        retriever=retriever,
        context_builder=context_builder,
        responder=responder,
        clarification=clarification,
        clarification_round_count=0,
    )

    assert clarification.called
    assert result["intent_decision"].intent_type == IntentType.AMBIGUOUS
    assert result["clarification_round_count"] == 1
    assert len(result["messages"]) == 1
    assert result["messages"][0].content == "Which document do you mean?"


def test_ambiguous_intent_forces_retriever_at_max_clarification_rounds():
    """Ambiguous intent at or above max clarification rounds forces retrieval path."""
    classifier = FakeClassifier(IntentType.AMBIGUOUS)
    retriever = RecordingRetriever()
    context_builder = RecordingContextBuilder()
    responder = RecordingResponder("Best effort answer after max clarification rounds.")
    clarification = _failing_node("clarification")

    result = invoke_full_graph(
        _successful_result(_normalized_input("status")),
        classifier=classifier,
        retriever=retriever,
        context_builder=context_builder,
        responder=responder,
        clarification=clarification,
        clarification_round_count=MAX_CLARIFICATION_ROUNDS,
    )

    assert retriever.called
    assert context_builder.called
    assert responder.called
    assert result["clarification_round_count"] == 0  # reset by _run_retriever_and_reset_clarification
    assert result["messages"][-1].content == "Best effort answer after max clarification rounds."


def test_invoke_full_graph_preserves_messages_and_summary():
    """Verify conversation history and summary are passed through into the graph state."""
    classifier = FakeClassifier(IntentType.GENERAL_CHAT)
    responder = RecordingResponder("I remember our conversation.")

    prior_messages = [
        HumanMessage(content="My name is Alex"),
        AIMessage(content="Nice to meet you Alex"),
    ]
    summary = "User's name is Alex."

    result = invoke_full_graph(
        _successful_result(_normalized_input("Do you know who I am?")),
        classifier=classifier,
        responder=responder,
        messages=prior_messages,
        conversation_summary=summary,
    )

    assert result["conversation_summary"] == summary
    # 2 prior messages + 1 new AI message = 3 messages
    assert len(result["messages"]) == 3
    assert result["messages"][0].content == "My name is Alex"
    assert result["messages"][1].content == "Nice to meet you Alex"
    assert result["messages"][2].content == "I remember our conversation."
