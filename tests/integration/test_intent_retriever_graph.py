import pytest

from app.contracts.intent_decision import IntentDecision, IntentType
from app.contracts.normalized_input import NormalizedInput
from app.graph.graph import invoke_intent_retriever_graph
from app.graph.routing import route_after_intent
from app.input_processing.schemas import InputProcessingResult


class FakeClassifier:
    def __init__(self, intent_type: IntentType) -> None:
        self.intent_type = intent_type
        self.query = None

    def classify(self, query: str) -> IntentDecision:
        self.query = query
        return IntentDecision(
            query="provider placeholder",
            intent_type=self.intent_type,
            confidence_score=0.95,
        )


class RecordingRetriever:
    def __init__(self) -> None:
        self.state = None

    def __call__(self, state: dict) -> dict:
        self.state = state
        return {"documents": ["retrieved-document"]}


def _normalized_input() -> NormalizedInput:
    return NormalizedInput(
        user_query="What documents are needed for PAN application?",
        image_content=[],
        pdf_content=[],
        combined_text="<USER_QUERY>\nWhat documents are needed for PAN application?",
    )


def _successful_result(normalized_input: NormalizedInput | None = None) -> InputProcessingResult:
    return InputProcessingResult(
        success=True,
        normalized_input=normalized_input or _normalized_input(),
    )


def _failing_retriever(state: dict) -> dict:
    raise AssertionError("retriever should not be called for this intent")


def test_document_info_routes_to_retriever_and_writes_documents() -> None:
    classifier = FakeClassifier(IntentType.DOCUMENT_INFO)
    retriever = RecordingRetriever()

    result = invoke_intent_retriever_graph(
        _successful_result(),
        classifier,
        retriever,
    )

    assert result["intent_decision"].intent_type == IntentType.DOCUMENT_INFO
    assert result["documents"] == ["retrieved-document"]
    assert retriever.state is not None


def test_general_chat_routes_to_placeholder_without_documents() -> None:
    result = invoke_intent_retriever_graph(
        _successful_result(),
        FakeClassifier(IntentType.GENERAL_CHAT),
        _failing_retriever,
    )

    assert result["intent_decision"].intent_type == IntentType.GENERAL_CHAT
    assert "documents" not in result


def test_ambiguous_routes_to_placeholder_without_documents() -> None:
    result = invoke_intent_retriever_graph(
        _successful_result(),
        FakeClassifier(IntentType.AMBIGUOUS),
        _failing_retriever,
    )

    assert result["intent_decision"].intent_type == IntentType.AMBIGUOUS
    assert "documents" not in result


def test_missing_normalized_input_fails_before_classification() -> None:
    classifier = FakeClassifier(IntentType.DOCUMENT_INFO)
    retriever = RecordingRetriever()

    with pytest.raises(ValueError, match="successful normalized_input is required"):
        invoke_intent_retriever_graph(
            InputProcessingResult(success=False),
            classifier,
            retriever,
        )

    assert classifier.query is None
    assert retriever.state is None


def test_missing_intent_decision_in_routing_raises_clear_error() -> None:
    with pytest.raises(ValueError, match="intent_decision is required for intent routing"):
        route_after_intent({})


def test_conversation_fields_are_preserved() -> None:
    messages = [{"role": "human", "content": "Earlier turn."}]
    conversation_summary = "Earlier conversation about PAN documents."

    result = invoke_intent_retriever_graph(
        _successful_result(),
        FakeClassifier(IntentType.GENERAL_CHAT),
        _failing_retriever,
        messages=messages,
        conversation_summary=conversation_summary,
    )

    assert result["messages"] == messages
    assert result["conversation_summary"] == conversation_summary


def test_retriever_receives_same_normalized_input_object() -> None:
    normalized_input = _normalized_input()
    retriever = RecordingRetriever()

    invoke_intent_retriever_graph(
        _successful_result(normalized_input),
        FakeClassifier(IntentType.DOCUMENT_INFO),
        retriever,
    )

    assert retriever.state is not None
    assert retriever.state["normalized_input"] is normalized_input
