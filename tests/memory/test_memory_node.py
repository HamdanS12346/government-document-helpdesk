"""Unit and integration tests for memory nodes and MemoryManager."""

from unittest.mock import MagicMock
from langchain_core.messages import AIMessage, HumanMessage
import pytest
from app.contracts.normalized_input import NormalizedInput
from app.memory.node import (
    MemoryManager,
    get_server_session_thread_id,
    load_memory_node,
    reset_server_session_thread_id,
    resolve_thread_id,
    save_memory_node,
    set_default_memory_manager,
)
from app.memory.repository import SupabaseMemoryRepository
from app.memory.summarizer import ConversationSummarizer
from app.memory.window_manager import ConversationWindowManager


def test_resolve_thread_id():
    """resolve_thread_id honors precedence: explicit > config > state > server default."""
    server_id = get_server_session_thread_id()

    # 1. Fallback to server default
    assert resolve_thread_id() == server_id

    # 2. State precedence
    state = {"thread_id": "state-thread-123"}
    assert resolve_thread_id(state=state) == "state-thread-123"

    # 3. Config precedence over state
    config = {"configurable": {"thread_id": "config-thread-456"}}
    assert resolve_thread_id(config=config, state=state) == "config-thread-456"

    # 4. Explicit precedence over config
    assert resolve_thread_id(config=config, state=state, explicit_thread_id="explicit-789") == "explicit-789"


def test_reset_server_session_thread_id():
    """reset_server_session_thread_id updates active ID for clean restarts."""
    id1 = get_server_session_thread_id()
    id2 = reset_server_session_thread_id()
    assert id1 != id2
    assert get_server_session_thread_id() == id2


def test_load_and_save_turn_below_threshold():
    """Turns below the 14-message hard threshold accumulate in active working memory without eviction."""
    repo = SupabaseMemoryRepository(supabase_url=None, supabase_key=None)
    mgr = MemoryManager(repository=repo)
    set_default_memory_manager(mgr)

    thread_id = "test-session-001"
    config = {"configurable": {"thread_id": thread_id}}

    # Turn 1: Save
    state_turn1 = {
        "normalized_input": NormalizedInput(
            user_query="What documents do I need for PAN?",
            image_content=[],
            pdf_content=[],
            combined_text="What documents do I need for PAN?",
        ),
        "response": "You need identity proof, address proof, and date of birth proof.",
    }

    save_res1 = mgr.save_turn(state_turn1, config=config)
    assert len(save_res1["messages"]) == 2
    assert save_res1["conversation_summary"] == ""

    # Load memory node
    loaded = mgr.load_memory({}, config=config)
    assert len(loaded["messages"]) == 2
    assert loaded["messages"][0].content == "What documents do I need for PAN?"
    assert loaded["messages"][1].content == "You need identity proof, address proof, and date of birth proof."


def test_turn_crossing_hard_threshold_triggers_summarization():
    """When active message count exceeds 14 (7 turns), the oldest 4 messages are summarized and evicted."""
    repo = SupabaseMemoryRepository(supabase_url=None, supabase_key=None)
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = AIMessage(
        content="Consolidated summary: User inquired about PAN application, required proofs, and fees."
    )
    summarizer = ConversationSummarizer(llm=mock_llm)
    mgr = MemoryManager(repository=repo, summarizer=summarizer)

    thread_id = "test-session-hard-threshold"
    config = {"configurable": {"thread_id": thread_id}}

    # Pre-populate 7 turns = 14 messages (exactly at hard threshold)
    for i in range(1, 8):
        repo.append_turn(
            thread_id=thread_id,
            human_message=HumanMessage(content=f"Question {i}"),
            ai_message=AIMessage(content=f"Answer {i}"),
        )

    # Verify at hard threshold: 14 active messages, watermark 0
    active, summary, watermark = repo.load_active_messages(thread_id)
    assert len(active) == 14
    assert watermark == 0
    assert not mock_llm.invoke.called

    # Turn 8 (Messages 15 and 16): Adding this breaches the hard threshold of 14
    state_turn8 = {
        "normalized_input": NormalizedInput(
            user_query="Question 8",
            image_content=[],
            pdf_content=[],
            combined_text="Question 8",
        ),
        "response": "Answer 8",
    }

    result = mgr.save_turn(state_turn8, config=config)

    # Assert summarizer was invoked
    assert mock_llm.invoke.called

    # 4 oldest messages (Questions 1 & 2) should be evicted; remaining count should be 16 - 4 = 12
    assert len(result["messages"]) == 12
    assert "Consolidated summary" in result["conversation_summary"]
    # Oldest message in remaining list should be Question 3
    assert result["messages"][0].content == "Question 3"
    assert result["messages"][-1].content == "Answer 8"

    # Verify repository watermark moved from 0 to 4
    _, repo_summary, repo_watermark = repo.load_active_messages(thread_id)
    assert repo_watermark == 4
    assert "Consolidated summary" in repo_summary
