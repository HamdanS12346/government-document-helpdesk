"""Unit tests for SupabaseMemoryRepository."""

from unittest.mock import MagicMock
from langchain_core.messages import AIMessage, HumanMessage
import pytest
from app.contracts.memory import MessageRole
from app.memory.repository import SupabaseMemoryRepository


def test_in_memory_thread_creation_and_append():
    """Repository creates threads and sequentially appends dialogue turns in memory mode."""
    repo = SupabaseMemoryRepository(supabase_url=None, supabase_key=None)

    thread = repo.get_or_create_thread("thread-001", title="Passport Application")
    assert thread.id == "thread-001"
    assert thread.last_summarized_seq == 0
    assert thread.conversation_summary == ""

    # Append turn 1
    u1 = HumanMessage(content="What are the documents for passport?")
    a1 = AIMessage(content="You need proof of date of birth and address.")
    user_msg, ai_msg = repo.append_turn("thread-001", u1, a1)

    assert user_msg.sequence_number == 1
    assert user_msg.role == MessageRole.HUMAN
    assert ai_msg.sequence_number == 2
    assert ai_msg.role == MessageRole.AI

    # Append turn 2
    u2 = HumanMessage(content="Is Aadhaar card accepted for address?")
    a2 = AIMessage(content="Yes, Aadhaar card is accepted as address proof.")
    u_msg2, a_msg2 = repo.append_turn("thread-001", u2, a2)

    assert u_msg2.sequence_number == 3
    assert a_msg2.sequence_number == 4


def test_active_messages_filtering_with_watermark():
    """Watermark strictly filters out summarized messages from active window."""
    repo = SupabaseMemoryRepository(supabase_url=None, supabase_key=None)
    thread_id = "thread-002"

    # Append 3 turns = 6 messages (seq 1 to 6)
    for i in range(1, 4):
        repo.append_turn(
            thread_id,
            HumanMessage(content=f"Question {i}"),
            AIMessage(content=f"Answer {i}"),
        )

    # Initial load: all 6 active, watermark 0
    active, summary, watermark = repo.load_active_messages(thread_id)
    assert len(active) == 6
    assert watermark == 0
    assert summary == ""

    # Advance watermark to 4 (summarizing turns 1 & 2 = messages 1..4)
    new_summary = "User asked questions 1 and 2 regarding document eligibility."
    repo.update_summary_watermark(thread_id, new_summary=new_summary, new_watermark=4)

    # Active messages should now only contain messages with seq > 4 (i.e. seq 5 and 6)
    active_post, summary_post, watermark_post = repo.load_active_messages(thread_id)
    assert len(active_post) == 2
    assert active_post[0].content == "Question 3"
    assert active_post[1].content == "Answer 3"
    assert watermark_post == 4
    assert summary_post == new_summary

    # Full transcript should still contain all 6 messages
    full_transcript = repo.get_full_transcript(thread_id)
    assert len(full_transcript) == 6


def test_mock_supabase_client_path():
    """Repository interacts properly with live Supabase client tables."""
    mock_client = MagicMock()

    # Mock conversation_threads select
    mock_thread_res = MagicMock()
    mock_thread_res.data = [
        {
            "id": "thread-cloud-001",
            "title": "Aadhaar",
            "status": "active",
            "conversation_summary": "Prior summary.",
            "last_summarized_seq": 2,
            "created_at": "2026-09-14T10:00:00Z",
            "updated_at": "2026-09-14T10:05:00Z",
        }
    ]
    mock_client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = mock_thread_res

    # Mock conversation_messages select
    mock_messages_res = MagicMock()
    mock_messages_res.data = [
        {
            "id": "msg-003",
            "thread_id": "thread-cloud-001",
            "role": "human",
            "content": "What is UIDAI?",
            "sequence_number": 3,
            "created_at": "2026-09-14T10:06:00Z",
        },
        {
            "id": "msg-004",
            "thread_id": "thread-cloud-001",
            "role": "ai",
            "content": "UIDAI is Unique Identification Authority of India.",
            "sequence_number": 4,
            "created_at": "2026-09-14T10:06:05Z",
        },
    ]
    mock_client.table.return_value.select.return_value.eq.return_value.gt.return_value.order.return_value.execute.return_value = mock_messages_res

    repo = SupabaseMemoryRepository(client=mock_client)
    assert repo.is_live is True

    active, summary, watermark = repo.load_active_messages("thread-cloud-001")
    assert len(active) == 2
    assert isinstance(active[0], HumanMessage)
    assert active[0].content == "What is UIDAI?"
    assert summary == "Prior summary."
    assert watermark == 2
