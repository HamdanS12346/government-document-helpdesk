"""Unit tests for memory data contracts."""

from datetime import datetime, timezone
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
import pytest
from app.contracts.memory import (
    ConversationMessage,
    ConversationThread,
    MemorySnapshot,
    MessageRole,
)


def test_conversation_message_langchain_conversion():
    """ConversationMessage correctly converts to and from LangChain messages."""
    human_msg = HumanMessage(content="What are the rules for Aadhaar update?")
    conv_msg = ConversationMessage.from_langchain(
        message=human_msg,
        thread_id="test-thread-123",
        sequence_number=1,
    )

    assert conv_msg.thread_id == "test-thread-123"
    assert conv_msg.role == MessageRole.HUMAN
    assert conv_msg.content == "What are the rules for Aadhaar update?"
    assert conv_msg.sequence_number == 1

    # Convert back to LangChain
    lc_back = conv_msg.to_langchain()
    assert isinstance(lc_back, HumanMessage)
    assert lc_back.content == "What are the rules for Aadhaar update?"

    # Test AI Message
    ai_msg = AIMessage(content="You must submit proof of identity and address.")
    conv_ai = ConversationMessage.from_langchain(
        message=ai_msg,
        thread_id="test-thread-123",
        sequence_number=2,
    )
    assert conv_ai.role == MessageRole.AI
    assert isinstance(conv_ai.to_langchain(), AIMessage)

    # Test System Message
    sys_msg = SystemMessage(content="Helpdesk initialized")
    conv_sys = ConversationMessage.from_langchain(
        message=sys_msg,
        thread_id="test-thread-123",
        sequence_number=0 if False else 1,
    )
    assert conv_sys.role == MessageRole.SYSTEM
    assert isinstance(conv_sys.to_langchain(), SystemMessage)


def test_conversation_thread_defaults_and_watermark():
    """ConversationThread validates sequence watermarks and default values."""
    thread = ConversationThread(
        id="thread-abc-001",
        title="PAN Card Linking",
    )

    assert thread.id == "thread-abc-001"
    assert thread.status == "active"
    assert thread.conversation_summary == ""
    assert thread.last_summarized_seq == 0

    # Advance watermark
    thread_advanced = thread.model_copy(
        update={
            "last_summarized_seq": 4,
            "conversation_summary": "User asked about PAN card linking procedure.",
        }
    )
    assert thread_advanced.last_summarized_seq == 4
    assert "PAN card linking" in thread_advanced.conversation_summary


def test_memory_snapshot_structure():
    """MemorySnapshot properly packages active message window and metadata."""
    snapshot = MemorySnapshot(
        thread_id="thread-xyz",
        active_messages=[
            HumanMessage(content="Query 1"),
            AIMessage(content="Answer 1"),
        ],
        conversation_summary="Prior context",
        last_summarized_seq=4,
        total_messages_count=6,
    )

    assert snapshot.thread_id == "thread-xyz"
    assert len(snapshot.active_messages) == 2
    assert snapshot.last_summarized_seq == 4
    assert snapshot.total_messages_count == 6
