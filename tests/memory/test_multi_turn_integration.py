"""Multi-turn integration tests verifying memory compatibility with Intent Classifier and Retriever Query Rewriter."""

from unittest.mock import MagicMock
from langchain_core.messages import AIMessage, HumanMessage
import pytest
from app.contracts.intent_decision import IntentDecision, IntentType
from app.contracts.normalized_input import NormalizedInput
from app.intent.classifier import IntentClassifier
from app.intent.query_builder import build_classification_query
from app.memory.node import MemoryManager
from app.memory.repository import SupabaseMemoryRepository
from app.rag.query_rewriter import QueryRewriter


def test_memory_context_integration_with_intent_query_builder():
    """Intent classification query builder seamlessly consumes memory-loaded messages and summary."""
    repo = SupabaseMemoryRepository(supabase_url=None, supabase_key=None)
    mgr = MemoryManager(repository=repo)

    thread_id = "integration-thread-intent"
    config = {"configurable": {"thread_id": thread_id}}

    # Turn 1: User asks about passport
    t1_state = {
        "normalized_input": NormalizedInput(
            user_query="Tell me about passport application requirements.",
            image_content=[],
            pdf_content=[],
            combined_text="Tell me about passport application requirements.",
        ),
        "response": "For a passport, you need proof of date of birth, photo ID, and address proof.",
    }
    mgr.save_turn(t1_state, config=config)

    # Turn 2: Follow-up query
    t2_loaded = mgr.load_memory({}, config=config)
    messages = t2_loaded["messages"]
    summary = t2_loaded["conversation_summary"]

    norm_input_t2 = NormalizedInput(
        user_query="Which address proofs are accepted?",
        image_content=[],
        pdf_content=[],
        combined_text="Which address proofs are accepted?",
    )

    query_str = build_classification_query(
        normalized_input=norm_input_t2,
        messages=messages,
        conversation_summary=summary,
    )

    # Assert conversation context is rendered for the classifier
    assert "User Query:\nWhich address proofs are accepted?" in query_str
    assert "Recent Conversation:" in query_str
    assert "human: Tell me about passport application requirements." in query_str
    assert "ai: For a passport, you need proof of date of birth" in query_str


def test_memory_context_integration_with_retriever_query_rewriter():
    """Retriever QueryRewriter uses memory-loaded messages and summary to resolve pronouns."""
    repo = SupabaseMemoryRepository(supabase_url=None, supabase_key=None)
    mgr = MemoryManager(repository=repo)

    thread_id = "integration-thread-retriever"
    config = {"configurable": {"thread_id": thread_id}}

    # Turn 1
    t1_state = {
        "normalized_input": NormalizedInput(
            user_query="I want to apply for a PAN card.",
            image_content=[],
            pdf_content=[],
            combined_text="I want to apply for a PAN card.",
        ),
        "response": "You can apply using Form 49A for Indian citizens or Form 49AA for foreign citizens.",
    }
    mgr.save_turn(t1_state, config=config)

    # Load memory for Turn 2
    t2_memory = mgr.load_memory({}, config=config)

    # Mock QueryRewriter LLM to check received prompt context
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = AIMessage(
        content="What is the application fee for an Indian PAN card using Form 49A?"
    )
    rewriter = QueryRewriter(llm=mock_llm)

    rewritten = rewriter.rewrite(
        user_query="What is the fee for the first one?",
        messages=t2_memory["messages"],
        conversation_summary=t2_memory["conversation_summary"],
    )

    assert "PAN card using Form 49A" in rewritten
    # Check that rewriter prompt received the dialogue from memory
    prompt_payload = mock_llm.invoke.call_args[0][0][1].content
    assert "User: I want to apply for a PAN card." in prompt_payload
    assert "Assistant: You can apply using Form 49A" in prompt_payload
    assert "Current User Query:\nWhat is the fee for the first one?" in prompt_payload
