import pytest

from app.contracts.intent_decision import IntentDecision
from app.contracts.normalized_input import NormalizedInput, PDFContent
from app.graph.graph import build_input_intent_graph, invoke_input_intent_graph
from app.input_processing.schemas import InputProcessingResult


class FakeClassifier:
    def __init__(self) -> None:
        self.query = None

    def classify(self, query: str) -> IntentDecision:
        self.query = query
        return IntentDecision(
            query="provider placeholder",
            intent_type="document_info",
            confidence_score=0.93,
        )


def _successful_result() -> InputProcessingResult:
    return InputProcessingResult(
        success=True,
        normalized_input=NormalizedInput(
            user_query="What does this notice mean?",
            image_content=[],
            pdf_content=[
                PDFContent(
                    pdf_name="notice.pdf",
                    extracted_text="Full extracted PDF text stays outside intent query.",
                    preview="Renewal notice: submit documents by June 30.",
                )
            ],
            combined_text=(
                "<USER_QUERY>\nWhat does this notice mean?\n\n"
                "<PDF_CONTENT>\nFull extracted PDF text stays outside intent query."
            ),
        ),
    )


def test_input_intent_graph_classifies_successful_normalized_input() -> None:
    classifier = FakeClassifier()
    graph = build_input_intent_graph(classifier)
    state = {
        "normalized_input": _successful_result().normalized_input,
        "messages": [{"role": "human", "content": "I uploaded a notice."}],
    }

    result = graph.invoke(state)

    assert result["normalized_input"] == state["normalized_input"]
    assert result["intent_decision"].intent_type == "document_info"
    assert result["intent_decision"].query == classifier.query
    assert "PDF Preview 1:" in classifier.query
    assert "Full extracted PDF text" not in classifier.query


def test_input_intent_graph_bridge_uses_input_processor_state_update() -> None:
    classifier = FakeClassifier()

    result = invoke_input_intent_graph(
        _successful_result(),
        classifier,
        messages=[{"role": "human", "content": "Earlier turn."}],
        conversation_summary="Earlier conversation about renewals.",
    )

    assert set(result) == {
        "normalized_input",
        "messages",
        "conversation_summary",
        "intent_decision",
    }
    assert result["messages"] == [{"role": "human", "content": "Earlier turn."}]
    assert result["conversation_summary"] == "Earlier conversation about renewals."
    assert "Recent Conversation:" in classifier.query
    assert "Older Conversation Summary:" in classifier.query


def test_input_intent_graph_bridge_rejects_failed_input_result() -> None:
    classifier = FakeClassifier()

    with pytest.raises(ValueError, match="successful normalized_input is required"):
        invoke_input_intent_graph(
            InputProcessingResult(success=False),
            classifier,
        )

    assert classifier.query is None
