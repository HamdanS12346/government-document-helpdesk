"""Tests for the response_node LangGraph state contract."""

from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.contracts.intent_decision import IntentDecision, IntentType
from app.contracts.normalized_input import NormalizedInput
from app.contracts.response import RetrievedContext
from app.response.generator import ResponseGenerator
from app.response.node import response_node


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_generator(text: str = "Here is your answer.") -> ResponseGenerator:
    gen = MagicMock(spec=ResponseGenerator)
    gen.generate.return_value = AIMessage(content=text)
    return gen


def _base_state() -> dict:
    return {
        "normalized_input": NormalizedInput(
            user_query="How do I apply for a ration card?",
            image_content=[],
            pdf_content=[],
            combined_text="How do I apply for a ration card?",
        ),
        "intent_decision": IntentDecision(
            query="How do I apply for a ration card?",
            intent_type=IntentType.GENERAL_CHAT,
            confidence_score=0.9,
        ),
    }


# ---------------------------------------------------------------------------
# Return value contract
# ---------------------------------------------------------------------------

class TestResponseNodeReturnContract:

    def test_returns_dict(self):
        result = response_node(_base_state(), generator=_mock_generator())
        assert isinstance(result, dict)

    def test_result_contains_messages_key(self):
        result = response_node(_base_state(), generator=_mock_generator())
        assert "messages" in result

    def test_messages_is_a_list(self):
        result = response_node(_base_state(), generator=_mock_generator())
        assert isinstance(result["messages"], list)

    def test_messages_contains_ai_message(self):
        result = response_node(_base_state(), generator=_mock_generator())
        assert any(isinstance(m, AIMessage) for m in result["messages"])

    def test_ai_message_content_is_non_empty(self):
        result = response_node(_base_state(), generator=_mock_generator("Some answer."))
        ai_msgs = [m for m in result["messages"] if isinstance(m, AIMessage)]
        assert ai_msgs[0].content == "Some answer."


class TestResponseNodeObservability:

    def test_logs_response_text_when_text_capture_enabled(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ):
        from app.config import get_settings
        import app.response.node as response_node_module

        updates: list[dict] = []

        class CapturingObservation:
            def update(self, **kwargs):
                updates.append(kwargs)

        @contextmanager
        def capture_observation(*args, **kwargs):
            yield CapturingObservation()

        monkeypatch.setenv("LANGFUSE_CAPTURE_TEXT", "true")
        get_settings.cache_clear()
        monkeypatch.setattr(
            response_node_module,
            "start_observation",
            capture_observation,
        )

        response_node(
            _base_state(),
            generator=_mock_generator("Here is the actual response."),
        )

        assert updates[-1]["output"]["response_chars"] == len(
            "Here is the actual response."
        )
        assert updates[-1]["output"]["response_text"] == (
            "Here is the actual response."
        )

    def test_omits_response_text_when_text_capture_disabled(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ):
        from app.config import get_settings
        import app.response.node as response_node_module

        updates: list[dict] = []

        class CapturingObservation:
            def update(self, **kwargs):
                updates.append(kwargs)

        @contextmanager
        def capture_observation(*args, **kwargs):
            yield CapturingObservation()

        monkeypatch.setenv("LANGFUSE_CAPTURE_TEXT", "false")
        get_settings.cache_clear()
        monkeypatch.setattr(
            response_node_module,
            "start_observation",
            capture_observation,
        )

        response_node(
            _base_state(),
            generator=_mock_generator("Here is the actual response."),
        )

        assert updates[-1]["output"]["response_chars"] == len(
            "Here is the actual response."
        )
        assert "response_text" not in updates[-1]["output"]

    def test_response_observation_input_includes_full_node_inputs(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ):
        from app.config import get_settings
        import app.response.node as response_node_module

        observations: list[dict] = []

        class CapturingObservation:
            def update(self, **kwargs):
                pass

        @contextmanager
        def capture_observation(*args, **kwargs):
            observations.append(kwargs)
            yield CapturingObservation()

        monkeypatch.setenv("LANGFUSE_CAPTURE_TEXT", "true")
        get_settings.cache_clear()
        monkeypatch.setattr(
            response_node_module,
            "start_observation",
            capture_observation,
        )

        state = _base_state()
        state["messages"] = [HumanMessage(content="Earlier question")]
        state["conversation_summary"] = "User asked about ration card documents."
        state["retrieved_context"] = RetrievedContext(
            formatted_context="[Document 1] Ration card application details.",
            sources=[],
            total_documents_retrieved=1,
            documents_used=1,
            has_relevant_documents=True,
            truncated=False,
            fallback_applied=False,
        )

        response_node(state, generator=_mock_generator())

        response_input = observations[-1]["input"]
        assert "normalized_input" in response_input
        assert "intent_decision" in response_input
        assert "retrieved_context" in response_input
        assert "messages" in response_input
        assert "conversation_summary" in response_input
        assert response_input["intent_decision"]["intent_type"] == "general_chat"
        assert response_input["messages"][0]["content_preview"] == "Earlier question"
        assert (
            response_input["retrieved_context"]["formatted_context_preview"]
            == "[Document 1] Ration card application details."
        )


# ---------------------------------------------------------------------------
# State reading
# ---------------------------------------------------------------------------

class TestResponseNodeStateReading:

    def test_missing_normalized_input_raises(self):
        state = _base_state()
        del state["normalized_input"]
        with pytest.raises(ValueError, match="normalized_input"):
            response_node(state, generator=_mock_generator())

    def test_missing_intent_decision_raises(self):
        state = _base_state()
        del state["intent_decision"]
        with pytest.raises(ValueError, match="intent_decision"):
            response_node(state, generator=_mock_generator())

    def test_missing_retrieved_context_handled_gracefully(self):
        """general_chat path — retrieved_context is absent."""
        state = _base_state()
        # No retrieved_context key at all
        result = response_node(state, generator=_mock_generator())
        assert "messages" in result

    def test_missing_messages_treated_as_empty(self):
        state = _base_state()
        # No messages key — first turn
        result = response_node(state, generator=_mock_generator())
        gen = _mock_generator()
        response_node(state, generator=gen)
        _, kwargs = gen.generate.call_args
        assert kwargs.get("messages") == [] or gen.generate.call_args[0][3] == []

    def test_missing_conversation_summary_handled_gracefully(self):
        state = _base_state()
        # No conversation_summary key
        result = response_node(state, generator=_mock_generator())
        assert "messages" in result

    def test_existing_messages_preserved_in_output(self):
        prior_msg = HumanMessage(content="Previous question")
        state = _base_state()
        state["messages"] = [prior_msg]

        result = response_node(state, generator=_mock_generator())
        # Prior message should still be in the output list
        assert prior_msg in result["messages"]

    def test_retrieved_context_passed_to_generator(self):
        gen = _mock_generator()
        retrieved = RetrievedContext(
            formatted_context="Doc content",
            sources=[],
            total_documents_retrieved=1,
            documents_used=1,
            has_relevant_documents=True,
            truncated=False,
            fallback_applied=False,
        )
        state = _base_state()
        state["retrieved_context"] = retrieved

        response_node(state, generator=gen)
        gen.generate.assert_called_once()
        call_kwargs = gen.generate.call_args.kwargs
        assert call_kwargs.get("retrieved_context") is retrieved


# ---------------------------------------------------------------------------
# Generator injection
# ---------------------------------------------------------------------------

class TestResponseNodeGeneratorInjection:

    def test_custom_generator_is_used(self):
        gen = _mock_generator("Custom response.")
        result = response_node(_base_state(), generator=gen)
        gen.generate.assert_called_once()
        ai_msgs = [m for m in result["messages"] if isinstance(m, AIMessage)]
        assert ai_msgs[0].content == "Custom response."

    def test_generator_called_with_correct_normalized_input(self):
        gen = _mock_generator()
        state = _base_state()
        response_node(state, generator=gen)
        kwargs = gen.generate.call_args.kwargs
        assert kwargs["normalized_input"] == state["normalized_input"]

    def test_generator_called_with_correct_intent_decision(self):
        gen = _mock_generator()
        state = _base_state()
        response_node(state, generator=gen)
        kwargs = gen.generate.call_args.kwargs
        assert kwargs["intent_decision"] == state["intent_decision"]
