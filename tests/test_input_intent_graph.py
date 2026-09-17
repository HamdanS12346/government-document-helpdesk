import pytest

from app.contracts.intent_decision import IntentDecision
from app.contracts.normalized_input import (
    ImageContent,
    NormalizedInput,
    PDFContent,
    SpreadsheetContent,
    SpreadsheetMetadata,
    SpreadsheetSheet,
)
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
            image_content=[
                ImageContent(
                    image_name="notice.png",
                    extracted_text="Full extracted image text stays outside intent query.",
                    preview="Photo preview: appointment date is listed.",
                )
            ],
            pdf_content=[
                PDFContent(
                    pdf_name="notice.pdf",
                    extracted_text="Full extracted PDF text stays outside intent query.",
                    preview="Renewal notice: submit documents by June 30.",
                )
            ],
            spreadsheet_content=[
                SpreadsheetContent(
                    workbook_name="notice.xlsx",
                    sheets=[
                        SpreadsheetSheet(
                            name="Renewals",
                            position=1,
                            max_row=1,
                            max_column=2,
                            is_empty=False,
                        )
                    ],
                    preview="Workbook preview: renewal fee is listed.",
                    warnings=[],
                    metadata=SpreadsheetMetadata(
                        workbook_name="notice.xlsx",
                        processed_sheet_count=1,
                        total_visible_sheet_count=1,
                        hidden_sheet_count=0,
                        max_sheets=5,
                        max_rows_per_sheet=50,
                        max_columns_per_sheet=50,
                        max_text_cell_characters=5000,
                        preview_row_count=5,
                    ),
                )
            ],
            combined_text=(
                "<USER_QUERY>\nWhat does this notice mean?\n\n"
                "<IMAGE_CONTENT>\nFull extracted image text stays outside intent query.\n\n"
                "<PDF_CONTENT>\nFull extracted PDF text stays outside intent query.\n\n"
                "<SPREADSHEET_CONTENT>\nFull spreadsheet projection stays outside intent query."
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
    assert "Image Preview 1:" in classifier.query
    assert "Photo preview: appointment date is listed." in classifier.query
    assert "PDF Preview 1:" in classifier.query
    assert "Renewal notice: submit documents by June 30." in classifier.query
    assert "Spreadsheet Preview 1:" in classifier.query
    assert "notice.xlsx: Workbook preview: renewal fee is listed." in classifier.query
    assert "Full extracted image text" not in classifier.query
    assert "Full extracted PDF text" not in classifier.query
    assert "Full spreadsheet projection" not in classifier.query
    assert "<IMAGE_CONTENT>" not in classifier.query
    assert "<PDF_CONTENT>" not in classifier.query
    assert "<SPREADSHEET_CONTENT>" not in classifier.query


def test_input_intent_graph_runs_with_only_normalized_input() -> None:
    classifier = FakeClassifier()
    graph = build_input_intent_graph(classifier)
    state = {"normalized_input": _successful_result().normalized_input}

    result = graph.invoke(state)

    assert set(result) == {"normalized_input", "intent_decision"}
    assert result["intent_decision"].query == classifier.query
    assert "Recent Conversation:" not in classifier.query
    assert "Older Conversation Summary:" not in classifier.query


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
