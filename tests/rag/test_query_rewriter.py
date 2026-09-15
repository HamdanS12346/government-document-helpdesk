"""Unit tests for QueryRewriter."""

from unittest.mock import MagicMock
from langchain_core.messages import AIMessage, HumanMessage
from app.rag.query_rewriter import QueryRewriter


def test_turn_one_bypass_no_context():
    """Turn 1 queries without context or attachments should bypass the LLM."""
    mock_llm = MagicMock()
    rewriter = QueryRewriter(llm=mock_llm)

    query = "What is the procedure for obtaining a PAN card?"
    result = rewriter.rewrite(user_query=query, messages=[], conversation_summary=None)

    assert result == query
    mock_llm.assert_not_called()


def test_rewrite_with_conversation_history():
    """Multi-turn references like 'the second one' should be rewritten via LLM."""
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = AIMessage(
        content="What are the eligibility criteria for presumptive taxation under Section 44ADA?"
    )
    rewriter = QueryRewriter(llm=mock_llm)

    messages = [
        HumanMessage(content="What presumptive taxation schemes are available under ITR-4?"),
        AIMessage(content="The available schemes are Section 44AD for business, 44ADA for professionals, and 44AE for goods carriages."),
    ]
    query = "What are the rules for the second one?"

    result = rewriter.rewrite(user_query=query, messages=messages)

    assert result == "What are the eligibility criteria for presumptive taxation under Section 44ADA?"
    mock_llm.invoke.assert_called_once()


def test_rewrite_with_attachment_previews():
    """Attachment previews should be injected into rewriter prompt."""
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = AIMessage(
        content="Can a Certificate of Residence be used as proof of address for passport application?"
    )
    rewriter = QueryRewriter(llm=mock_llm)

    previews = ["Certificate of Residence\nName: Rahul Sharma\nAddress: Sector 12"]
    query = "Can I use this as proof of address for passport?"

    result = rewriter.rewrite(
        user_query=query,
        messages=[],
        attachment_previews=previews,
    )

    assert "Certificate of Residence" in result
    mock_llm.invoke.assert_called_once()


def test_fallback_on_llm_exception():
    """If LLM fails, rewriter gracefully falls back to the original user query."""
    mock_llm = MagicMock()
    mock_llm.invoke.side_effect = RuntimeError("OpenAI API rate limit exceeded")
    rewriter = QueryRewriter(llm=mock_llm)

    messages = [HumanMessage(content="Hello")]
    query = "What is this?"

    result = rewriter.rewrite(user_query=query, messages=messages)

    assert result == query
