"""Tests for Langfuse observability helpers."""

import pytest

from app.config import Settings, get_settings
from app.contracts.intent_decision import IntentDecision, IntentType
from app.contracts.normalized_input import NormalizedInput
from app.contracts.response import RetrievedContext
from app.observability.metadata import (
    TEXT_PREVIEW_MAX_CHARS,
    build_clarification_input_metadata,
    build_clarification_output_metadata,
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
