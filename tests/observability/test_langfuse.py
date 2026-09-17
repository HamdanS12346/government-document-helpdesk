"""Tests for Langfuse observability helpers."""

import pytest

from app.config import Settings, get_settings
from app.contracts.intent_decision import IntentDecision, IntentType
from app.contracts.normalized_input import (
    NormalizedInput,
    SpreadsheetContent,
    SpreadsheetMetadata,
    SpreadsheetSheet,
)
from app.input_processing.schemas import (
    Attachment,
    AttachmentProcessingStatus,
    InputProcessingResult,
    InputRequest,
)
from app.contracts.response import RetrievedContext
from app.observability.metadata import (
    TEXT_PREVIEW_MAX_CHARS,
    build_chat_graph_response_metadata,
    build_chat_request_metadata,
    build_clarification_input_metadata,
    build_clarification_output_metadata,
    build_input_processing_result_metadata,
    build_input_request_metadata,
    build_normalized_input_metadata,
    build_retrieved_context_metadata,
)
from app.observability import langfuse as langfuse_module
from app.observability.langfuse import (
    NoOpObservation,
    flush_langfuse,
    get_langfuse_client,
    start_observation,
)


def teardown_function() -> None:
    get_settings.cache_clear()
    get_langfuse_client.cache_clear()


SPREADSHEET_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)


def _spreadsheet_content() -> SpreadsheetContent:
    return SpreadsheetContent(
        workbook_name="benefits.xlsx",
        sheets=[
            SpreadsheetSheet(
                name="Applicants",
                position=1,
                max_row=2,
                max_column=2,
                is_empty=False,
            )
        ],
        preview="Workbook: benefits.xlsx\nSheet: Applicants\nRow 1: PAN ABCDE1234F",
        warnings=["Hidden spreadsheet content was excluded."],
        metadata=SpreadsheetMetadata(
            workbook_name="benefits.xlsx",
            processed_sheet_count=1,
            total_visible_sheet_count=2,
            hidden_sheet_count=1,
            max_sheets=5,
            max_rows_per_sheet=50,
            max_columns_per_sheet=50,
            max_text_cell_characters=5000,
            preview_row_count=5,
        ),
    )


class FakeUploadFile:
    def __init__(self, content_type: str) -> None:
        self.content_type = content_type


def test_langfuse_settings_support_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANGFUSE_ENABLED", "true")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    monkeypatch.setenv("LANGFUSE_BASE_URL", "https://langfuse.example")
    monkeypatch.delenv("LANGFUSE_HOST", raising=False)

    settings = Settings(_env_file=None)

    assert settings.langfuse_enabled is True
    assert settings.langfuse_public_key == "pk-test"
    assert settings.langfuse_secret_key == "sk-test"
    assert settings.langfuse_base_url == "https://langfuse.example"


def test_langfuse_settings_support_host_alias(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LANGFUSE_ENABLED", "true")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    monkeypatch.delenv("LANGFUSE_BASE_URL", raising=False)
    monkeypatch.setenv("LANGFUSE_HOST", "https://legacy-langfuse.example")

    settings = Settings(_env_file=None)

    assert settings.langfuse_base_url == "https://legacy-langfuse.example"


def test_langfuse_client_is_none_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LANGFUSE_ENABLED", "false")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    get_settings.cache_clear()
    get_langfuse_client.cache_clear()

    assert get_langfuse_client() is None


def test_start_observation_noops_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LANGFUSE_ENABLED", "false")
    get_settings.cache_clear()
    get_langfuse_client.cache_clear()

    with start_observation("chat_request") as observation:
        assert isinstance(observation, NoOpObservation)
        observation.update(metadata={"status": "ok"})


def test_start_observation_reraises_application_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LANGFUSE_ENABLED", "false")
    get_settings.cache_clear()
    get_langfuse_client.cache_clear()

    with pytest.raises(RuntimeError, match="application failure"):
        with start_observation("chat_request"):
            raise RuntimeError("application failure")


def test_start_observation_uses_langfuse_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = FakeLangfuseClient()
    monkeypatch.setattr(
        langfuse_module,
        "get_langfuse_client",
        lambda: fake_client,
    )

    with start_observation(
        "chat_request",
        input={"route": "/chat"},
        metadata={"status": "started"},
    ) as observation:
        observation.update(output={"status": "success"})

    assert fake_client.started_kwargs == {
        "name": "chat_request",
        "as_type": "span",
        "input": {"route": "/chat"},
        "metadata": {"status": "started"},
    }
    assert fake_client.manager.observation.updates == [
        {"output": {"status": "success"}}
    ]
    assert fake_client.manager.exited is True


def test_chat_request_metadata_counts_spreadsheet_uploads() -> None:
    metadata = build_chat_request_metadata(
        "Review the attachments",
        [
            FakeUploadFile("image/png"),
            FakeUploadFile("application/pdf"),
            FakeUploadFile(SPREADSHEET_MEDIA_TYPE),
        ],
    )

    assert metadata["attachment_count"] == 3
    assert metadata["image_count"] == 1
    assert metadata["pdf_count"] == 1
    assert metadata["spreadsheet_count"] == 1
    assert metadata["attachment_media_types"] == [
        "image/png",
        "application/pdf",
        SPREADSHEET_MEDIA_TYPE,
    ]


def test_input_request_metadata_counts_spreadsheet_uploads() -> None:
    metadata = build_input_request_metadata(
        InputRequest(
            user_query="Review this workbook",
            attachments=[
                Attachment(
                    filename="benefits.xlsx",
                    media_type=SPREADSHEET_MEDIA_TYPE,
                    content=b"raw workbook bytes",
                )
            ],
        )
    )

    assert metadata["attachment_count"] == 1
    assert metadata["image_count"] == 0
    assert metadata["pdf_count"] == 0
    assert metadata["spreadsheet_count"] == 1
    assert "raw workbook bytes" not in str(metadata)
    assert "benefits.xlsx" not in str(metadata)


def test_input_processing_result_metadata_reports_spreadsheet_counts_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LANGFUSE_CAPTURE_TEXT", "false")
    get_settings.cache_clear()
    spreadsheet = _spreadsheet_content()

    metadata = build_input_processing_result_metadata(
        InputProcessingResult(
            success=True,
            normalized_input=NormalizedInput(
                user_query="Review this workbook",
                image_content=[],
                pdf_content=[],
                spreadsheet_content=[spreadsheet],
                combined_text="<SPREADSHEET_CONTENT>\nPAN ABCDE1234F",
            ),
            attachment_statuses=[
                AttachmentProcessingStatus(
                    filename="benefits.xlsx",
                    status="success",
                )
            ],
        )
    )

    assert metadata["spreadsheet_content_count"] == 1
    assert metadata["spreadsheet_preview_lengths"] == [len(spreadsheet.preview)]
    assert metadata["spreadsheet_processed_sheet_counts"] == [1]
    assert metadata["spreadsheet_visible_sheet_counts"] == [2]
    assert metadata["spreadsheet_hidden_sheet_counts"] == [1]
    assert metadata["spreadsheet_warning_counts"] == [1]
    assert metadata["attachment_statuses"] == [
        {
            "filename": "benefits.xlsx",
            "status": "success",
            "error_code": None,
            "warning_count": 0,
        }
    ]
    assert "ABCDE1234F" not in str(metadata)
    assert "Applicants" not in str(metadata)


def test_normalized_input_metadata_reports_spreadsheet_counts_without_preview_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LANGFUSE_CAPTURE_TEXT", "true")
    get_settings.cache_clear()
    spreadsheet = _spreadsheet_content()

    metadata = build_normalized_input_metadata(
        NormalizedInput(
            user_query="PAN ABCDE1234F",
            image_content=[],
            pdf_content=[],
            spreadsheet_content=[spreadsheet],
            combined_text="<USER_QUERY>\nPAN ABCDE1234F",
        )
    )

    assert metadata["spreadsheet_content_count"] == 1
    assert metadata["spreadsheet_preview_lengths"] == [len(spreadsheet.preview)]
    assert metadata["spreadsheet_processed_sheet_counts"] == [1]
    assert metadata["spreadsheet_visible_sheet_counts"] == [2]
    assert metadata["spreadsheet_hidden_sheet_counts"] == [1]
    assert metadata["spreadsheet_warning_counts"] == [1]
    assert metadata["normalized_user_query_preview"] == "PAN [REDACTED]"
    assert metadata["combined_text_preview"] == "<USER_QUERY>\nPAN [REDACTED]"
    assert "spreadsheet_previews" not in metadata
    assert "ABCDE1234F" not in str(metadata)
    assert "Applicants" not in str(metadata)


def test_flush_langfuse_uses_client_flush(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_client = FakeLangfuseClient()
    monkeypatch.setattr(
        langfuse_module,
        "get_langfuse_client",
        lambda: fake_client,
    )

    flush_langfuse()

    assert fake_client.flushed is True


def test_text_capture_is_omitted_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LANGFUSE_CAPTURE_TEXT", "false")
    get_settings.cache_clear()

    metadata = build_normalized_input_metadata(
        NormalizedInput(
            user_query="PAN ABCDE1234F",
            image_content=[],
            pdf_content=[],
            combined_text="<USER_QUERY>\nPAN ABCDE1234F",
        )
    )

    assert "normalized_user_query_preview" not in metadata
    assert "combined_text_preview" not in metadata


def test_text_capture_is_redacted_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LANGFUSE_CAPTURE_TEXT", "true")
    get_settings.cache_clear()

    metadata = build_normalized_input_metadata(
        NormalizedInput(
            user_query="PAN ABCDE1234F",
            image_content=[],
            pdf_content=[],
            combined_text="<USER_QUERY>\nPAN ABCDE1234F",
        )
    )

    assert metadata["normalized_user_query_preview"] == "PAN [REDACTED]"
    assert metadata["combined_text_preview"] == "<USER_QUERY>\nPAN [REDACTED]"


def test_text_capture_is_bounded_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LANGFUSE_CAPTURE_TEXT", "true")
    get_settings.cache_clear()

    metadata = build_retrieved_context_metadata(
        RetrievedContext(
            formatted_context="x" * (TEXT_PREVIEW_MAX_CHARS + 10),
            sources=[],
        )
    )

    assert len(metadata["formatted_context_preview"]) > TEXT_PREVIEW_MAX_CHARS
    assert metadata["formatted_context_preview"].endswith("... [truncated]")


def test_clarification_metadata_omits_text_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LANGFUSE_CAPTURE_TEXT", "false")
    get_settings.cache_clear()
    decision = IntentDecision(
        query="Need PAN ABCDE1234F help",
        intent_type=IntentType.AMBIGUOUS,
        confidence_score=0.41,
    )

    input_metadata = build_clarification_input_metadata(
        decision,
        messages=[{"role": "human", "content": "PAN ABCDE1234F"}],
        conversation_summary="Older PAN ABCDE1234F context",
        clarification_round_count=2,
        max_clarification_rounds=3,
    )
    output_metadata = build_clarification_output_metadata(
        clarification_required=True,
        reason_code="missing_location",
        missing_dimensions=["location"],
        question="Which state are you applying in? PAN ABCDE1234F",
    )

    assert input_metadata == {
        "intent_type": "ambiguous",
        "confidence_score": 0.41,
        "classification_query_length": len("Need PAN ABCDE1234F help"),
        "messages_count": 1,
        "has_conversation_summary": True,
        "conversation_summary_length": len("Older PAN ABCDE1234F context"),
        "clarification_round_count": 2,
        "max_clarification_rounds": 3,
    }
    assert "classification_query_preview" not in input_metadata
    assert "conversation_summary_preview" not in input_metadata
    assert output_metadata["question_length"] == len(
        "Which state are you applying in? PAN ABCDE1234F"
    )
    assert output_metadata["next_node_after_user_reply"] == "intent_classifier"
    assert "question_preview" not in output_metadata


def test_clarification_metadata_redacts_text_when_capture_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LANGFUSE_CAPTURE_TEXT", "true")
    get_settings.cache_clear()
    decision = IntentDecision(
        query="Need PAN ABCDE1234F help",
        intent_type=IntentType.AMBIGUOUS,
        confidence_score=0.41,
    )

    input_metadata = build_clarification_input_metadata(
        decision,
        conversation_summary="Older PAN ABCDE1234F context",
    )
    output_metadata = build_clarification_output_metadata(
        clarification_required=True,
        reason_code="missing_location",
        missing_dimensions=["location"],
        question="Which state are you applying in? PAN ABCDE1234F",
    )

    assert input_metadata["classification_query_preview"] == "Need PAN [REDACTED] help"
    assert input_metadata["conversation_summary_preview"] == (
        "Older PAN [REDACTED] context"
    )
    assert output_metadata["question_preview"] == (
        "Which state are you applying in? PAN [REDACTED]"
    )


def test_clarification_metadata_text_capture_is_bounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LANGFUSE_CAPTURE_TEXT", "true")
    get_settings.cache_clear()
    decision = IntentDecision(
        query="x" * (TEXT_PREVIEW_MAX_CHARS + 10),
        intent_type=IntentType.AMBIGUOUS,
        confidence_score=0.41,
    )

    input_metadata = build_clarification_input_metadata(decision)
    output_metadata = build_clarification_output_metadata(
        clarification_required=True,
        reason_code="unclear_request",
        missing_dimensions=["request"],
        question="y" * (TEXT_PREVIEW_MAX_CHARS + 10),
    )

    assert input_metadata["classification_query_preview"].endswith(
        "... [truncated]"
    )
    assert output_metadata["question_preview"].endswith("... [truncated]")


def test_chat_graph_response_metadata_reports_clarification_without_text_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LANGFUSE_CAPTURE_TEXT", "false")
    get_settings.cache_clear()
    question = "Which state are you applying in? PAN ABCDE1234F"

    metadata = build_chat_graph_response_metadata(
        {
            "intent_decision": IntentDecision(
                query="Need PAN ABCDE1234F help",
                intent_type=IntentType.AMBIGUOUS,
                confidence_score=0.41,
            ),
            "clarification_round_count": 2,
        },
        status="clarification_required",
        assistant_message_content=question,
    )

    assert metadata == {
        "status": "clarification_required",
        "has_intent_decision": True,
        "has_documents": False,
        "has_retrieved_context": False,
        "intent_type": "ambiguous",
        "confidence_score": 0.41,
        "classification_query_length": len("Need PAN ABCDE1234F help"),
        "assistant_message_length": len(question),
        "clarification_round_count": 2,
    }
    assert "assistant_message_preview" not in metadata
    assert "classification_query_preview" not in metadata


def test_chat_graph_response_metadata_redacts_text_when_capture_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LANGFUSE_CAPTURE_TEXT", "true")
    get_settings.cache_clear()

    metadata = build_chat_graph_response_metadata(
        {
            "intent_decision": IntentDecision(
                query="Need PAN ABCDE1234F help",
                intent_type=IntentType.AMBIGUOUS,
                confidence_score=0.41,
            ),
        },
        status="clarification_required",
        assistant_message_content="Which state? PAN ABCDE1234F",
    )

    assert metadata["classification_query_preview"] == "Need PAN [REDACTED] help"
    assert metadata["assistant_message_preview"] == "Which state? PAN [REDACTED]"


class FakeObservation:
    def __init__(self) -> None:
        self.updates: list[dict[str, object]] = []

    def update(self, **kwargs: object) -> None:
        self.updates.append(kwargs)


class FakeObservationManager:
    def __init__(self) -> None:
        self.observation = FakeObservation()
        self.exited = False

    def __enter__(self) -> FakeObservation:
        return self.observation

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.exited = True


class FakeLangfuseClient:
    def __init__(self) -> None:
        self.manager = FakeObservationManager()
        self.started_kwargs: dict[str, object] | None = None
        self.flushed = False

    def start_as_current_observation(self, **kwargs: object) -> FakeObservationManager:
        self.started_kwargs = kwargs
        return self.manager

    def flush(self) -> None:
        self.flushed = True
