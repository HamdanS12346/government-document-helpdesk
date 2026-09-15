"""Unit tests for ConversationSummarizer."""

from unittest.mock import MagicMock
from langchain_core.messages import AIMessage, HumanMessage
import pytest
from app.memory.summarizer import ConversationSummarizer


def test_summarize_empty_messages():
    """Summarizing empty message list simply returns the existing summary."""
    summarizer = ConversationSummarizer()
    res = summarizer.summarize([], existing_summary="Existing context.")
    assert res == "Existing context."


def test_summarize_invokes_llm_with_merged_context():
    """Summarizer properly passes existing summary and dialogue turns to LLM."""
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = AIMessage(
        content="Citizen inquired about driving license renewal and required medical certificates."
    )

    summarizer = ConversationSummarizer(llm=mock_llm)
    messages = [
        HumanMessage(content="How do I renew my driving license?"),
        AIMessage(content="You can apply online on Parivahan portal with Form 9."),
        HumanMessage(content="Is a medical certificate required?"),
        AIMessage(content="Yes, Form 1A is required for commercial or age > 40."),
    ]

    summary = summarizer.summarize(
        messages_to_summarize=messages,
        existing_summary="User asked about learner license.",
    )

    assert mock_llm.invoke.called
    assert "driving license renewal" in summary
    assert mock_llm.invoke.call_args[0][0][1].content.count("### EXISTING SUMMARY:") == 1
    assert mock_llm.invoke.call_args[0][0][1].content.count("### NEW CONVERSATION TURNS") == 1


def test_summarize_fallback_on_exception():
    """Summarizer falls back gracefully if LLM invocation raises an exception."""
    mock_llm = MagicMock()
    mock_llm.invoke.side_effect = RuntimeError("OpenAI rate limit exceeded")

    summarizer = ConversationSummarizer(llm=mock_llm)
    messages = [
        HumanMessage(content="What are the rules for voter ID?"),
        AIMessage(content="You must submit Form 6."),
    ]

    summary = summarizer.summarize(
        messages_to_summarize=messages,
        existing_summary="Previous summary.",
    )

    assert "Previous summary." in summary
    assert "Previous topics: 2 turns" in summary
