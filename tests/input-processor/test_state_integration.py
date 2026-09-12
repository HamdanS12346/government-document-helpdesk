"""Graph state integration tests for normalized input."""

from app.graph.state import GraphState
from app.input_processing.processors import build_graph_state_update, process_input
from app.input_processing.schemas import Attachment, InputRequest


def test_input_processor_writes_only_normalized_input_to_graph_state() -> None:
    result = process_input(InputRequest(user_query="What does this notice mean?"))

    state_update = build_graph_state_update(result)

    assert state_update.keys() == {"normalized_input"}
    assert state_update["normalized_input"].user_query == "What does this notice mean?"
    assert state_update["normalized_input"].combined_text == (
        "What does this notice mean?"
    )


def test_graph_state_update_excludes_raw_upload_objects_and_processing_result() -> None:
    result = process_input(
        InputRequest(
            user_query="Please review this.",
            attachments=[
                Attachment(
                    filename="bad.pdf",
                    media_type="application/pdf",
                    content=b"private raw upload bytes",
                )
            ],
        )
    )

    state_update = build_graph_state_update(result)

    assert state_update.keys() == {"normalized_input"}
    state_text = str(state_update)
    assert "private raw upload bytes" not in state_text
    assert "Attachment(" not in state_text
    assert "InputProcessingResult" not in state_text
    assert "attachment_statuses" not in state_text
    assert "raw_attachment_bytes" not in state_text
    assert "temporary_path" not in state_text
    assert "ocr_provider" not in state_text
    assert "pdf_extractor" not in state_text


def test_failed_input_processing_result_does_not_write_graph_state() -> None:
    result = process_input(InputRequest())

    state_update = build_graph_state_update(result)

    assert result.success is False
    assert state_update == {}


def test_downstream_nodes_can_read_normalized_input_fields_from_graph_state() -> None:
    result = process_input(InputRequest(user_query="Explain renewal steps."))
    state: GraphState = build_graph_state_update(result)

    normalized_input = state["normalized_input"]

    assert normalized_input.user_query == "Explain renewal steps."
    assert normalized_input.image_content == []
    assert normalized_input.pdf_content == []
    assert normalized_input.combined_text == "Explain renewal steps."


def test_graph_state_contains_no_raw_attachment_bytes_after_success() -> None:
    result = process_input(
        InputRequest(
            user_query="Use text only after bad upload.",
            attachments=[
                Attachment(
                    filename="raw-private.pdf",
                    media_type="application/pdf",
                    content=b"raw private attachment bytes",
                )
            ],
        )
    )

    state_update = build_graph_state_update(result)

    assert result.success is True
    assert state_update.keys() == {"normalized_input"}
    assert "raw private attachment bytes" not in str(state_update)
    assert "content" not in state_update
    assert "attachments" not in state_update


def test_graph_state_contains_no_upload_objects_or_temporary_paths() -> None:
    result = process_input(InputRequest(user_query="State boundary check."))

    state_update = build_graph_state_update(result)

    assert state_update.keys() == {"normalized_input"}
    assert "upload_file" not in state_update
    assert "UploadFile" not in str(state_update)
    assert "file_path" not in state_update
    assert "temporary_path" not in state_update
    assert "tmp" not in state_update


def test_input_processing_result_does_not_leak_into_graph_state() -> None:
    result = process_input(InputRequest(user_query="No result object in graph."))

    state_update = build_graph_state_update(result)

    assert state_update.keys() == {"normalized_input"}
    assert result not in state_update.values()
    assert "InputProcessingResult" not in str(state_update)
    assert "success" not in state_update
    assert "attachment_statuses" not in state_update
    assert "warnings" not in state_update
