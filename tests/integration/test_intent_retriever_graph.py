import pytest
from langchain_core.messages import AIMessage

from app.contracts.intent_decision import IntentDecision, IntentType
from app.contracts.normalized_input import NormalizedInput
from app.contracts.response import RetrievedContext
from app.graph.graph import invoke_intent_retriever_graph
from app.graph.routing import MAX_CLARIFICATION_ROUNDS, route_after_intent
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
        return {
            "documents": [
                {
                    "id": "identity-documents__pan-card__chunk-0001",
                    "text_content": "PAN application requires proof of identity.",
                    "metadata": {
                        "document_id": "identity-documents__pan-card",
                        "category": "identity-documents",
                        "document_name": "pan-card",
                    },
                    "score": 0.91,
                }
            ]
        }


class RecordingContextBuilder:
    def __init__(self) -> None:
        self.state = None

    def __call__(self, state: dict) -> dict:
        self.state = state
        return {
            "retrieved_context": {
                "formatted_context": "[Document 1]\nContent:\nPAN application requires proof of identity.",
                "sources": [],
            }
        }


class RecordingClarification:
    def __init__(self) -> None:
        self.state = None

    def __call__(self, state: dict) -> dict:
        self.state = state
        return {
            "messages": [AIMessage(content="Which document do you mean?")],
            "clarification_round_count": state.get("clarification_round_count", 0) + 1,
        }


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


def _failing_context_builder(state: dict) -> dict:
    raise AssertionError("context builder should not be called for this intent")


def _failing_clarification(state: dict) -> dict:
    raise AssertionError("clarification should not be called after limit")


def test_document_info_routes_to_retriever_context_builder_and_writes_state() -> None:
    classifier = FakeClassifier(IntentType.DOCUMENT_INFO)
    retriever = RecordingRetriever()
    context_builder = RecordingContextBuilder()

    result = invoke_intent_retriever_graph(
        _successful_result(),
        classifier,
        retriever,
        context_builder,
    )

    assert result["intent_decision"].intent_type == IntentType.DOCUMENT_INFO
    assert result["documents"][0]["id"] == "identity-documents__pan-card__chunk-0001"
    assert result["retrieved_context"]["formatted_context"].startswith("[Document 1]")
    assert retriever.state is not None
    assert context_builder.state is not None
    assert context_builder.state["documents"] == result["documents"]
    assert result["clarification_round_count"] == 0


def test_document_info_default_context_builder_formats_retrieved_documents() -> None:
    result = invoke_intent_retriever_graph(
        _successful_result(),
        FakeClassifier(IntentType.DOCUMENT_INFO),
        RecordingRetriever(),
    )

    retrieved_context = result["retrieved_context"]
    assert isinstance(retrieved_context, RetrievedContext)
    assert retrieved_context.documents_used == 1
    assert "[Document 1]" in retrieved_context.formatted_context
    assert "PAN application requires proof of identity." in (
        retrieved_context.formatted_context
    )
    assert retrieved_context.sources[0].chunk_id == (
        "identity-documents__pan-card__chunk-0001"
    )


def test_general_chat_routes_to_placeholder_without_documents() -> None:
    result = invoke_intent_retriever_graph(
        _successful_result(),
        FakeClassifier(IntentType.GENERAL_CHAT),
        _failing_retriever,
        _failing_context_builder,
        clarification_round_count=2,
    )

    assert result["intent_decision"].intent_type == IntentType.GENERAL_CHAT
    assert result["clarification_round_count"] == 0
    assert "documents" not in result
    assert "retrieved_context" not in result


@pytest.mark.parametrize("round_count", [0, 1, 2])
def test_ambiguous_routes_to_clarification_for_first_three_rounds(
    round_count: int,
) -> None:
    clarification = RecordingClarification()

    result = invoke_intent_retriever_graph(
        _successful_result(),
        FakeClassifier(IntentType.AMBIGUOUS),
        _failing_retriever,
        _failing_context_builder,
        clarification,
        clarification_round_count=round_count,
    )

    assert result["intent_decision"].intent_type == IntentType.AMBIGUOUS
    assert clarification.state is not None
    assert isinstance(result["messages"][0], AIMessage)
    assert result["messages"][0].content == "Which document do you mean?"
    assert result["clarification_round_count"] == round_count + 1
    assert "documents" not in result
    assert "retrieved_context" not in result


def test_ambiguous_routes_to_retriever_after_clarification_limit() -> None:
    retriever = RecordingRetriever()
    context_builder = RecordingContextBuilder()

    result = invoke_intent_retriever_graph(
        _successful_result(),
        FakeClassifier(IntentType.AMBIGUOUS),
        retriever,
        context_builder,
        _failing_clarification,
        clarification_round_count=MAX_CLARIFICATION_ROUNDS,
    )

    assert result["intent_decision"].intent_type == IntentType.AMBIGUOUS
    assert retriever.state is not None
    assert context_builder.state is not None
    assert result["documents"][0]["id"] == "identity-documents__pan-card__chunk-0001"
    assert result["clarification_round_count"] == 0


def test_missing_normalized_input_fails_before_classification() -> None:
    classifier = FakeClassifier(IntentType.DOCUMENT_INFO)
    retriever = RecordingRetriever()
    context_builder = RecordingContextBuilder()

    with pytest.raises(ValueError, match="successful normalized_input is required"):
        invoke_intent_retriever_graph(
            InputProcessingResult(success=False),
            classifier,
            retriever,
            context_builder,
        )

    assert classifier.query is None
    assert retriever.state is None
    assert context_builder.state is None


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
        _failing_context_builder,
        messages=messages,
        conversation_summary=conversation_summary,
    )

    assert result["messages"] == messages
    assert result["conversation_summary"] == conversation_summary


def test_retriever_receives_same_normalized_input_object() -> None:
    normalized_input = _normalized_input()
    retriever = RecordingRetriever()
    context_builder = RecordingContextBuilder()

    invoke_intent_retriever_graph(
        _successful_result(normalized_input),
        FakeClassifier(IntentType.DOCUMENT_INFO),
        retriever,
        context_builder,
    )

    assert retriever.state is not None
    assert retriever.state["normalized_input"] is normalized_input


def test_context_builder_receives_same_normalized_input_object() -> None:
    normalized_input = _normalized_input()
    context_builder = RecordingContextBuilder()

    invoke_intent_retriever_graph(
        _successful_result(normalized_input),
        FakeClassifier(IntentType.DOCUMENT_INFO),
        RecordingRetriever(),
        context_builder,
    )

    assert context_builder.state is not None
    assert context_builder.state["normalized_input"] is normalized_input
