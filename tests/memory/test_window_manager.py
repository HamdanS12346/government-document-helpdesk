"""Unit tests for ConversationWindowManager."""

from langchain_core.messages import AIMessage, HumanMessage
import pytest
from app.memory.window_manager import (
    EVICTION_BATCH_SIZE,
    HARD_THRESHOLD_MESSAGES,
    SOFT_THRESHOLD_MESSAGES,
    ConversationWindowManager,
)


def create_turn_pairs(num_pairs: int) -> list:
    """Helper to generate N user-assistant message pairs."""
    messages = []
    for i in range(1, num_pairs + 1):
        messages.append(HumanMessage(content=f"User question {i}"))
        messages.append(AIMessage(content=f"Assistant answer {i}"))
    return messages


def test_threshold_states():
    """WindowManager accurately flags soft and hard threshold boundaries."""
    mgr = ConversationWindowManager()

    # 4 pairs = 8 messages (below soft threshold)
    msgs_8 = create_turn_pairs(4)
    assert len(msgs_8) == 8
    assert not mgr.is_above_soft_threshold(msgs_8)
    assert not mgr.should_summarize(msgs_8)

    # 5 pairs = 10 messages (at soft threshold 10)
    msgs_10 = create_turn_pairs(5)
    assert len(msgs_10) == 10
    assert mgr.is_above_soft_threshold(msgs_10)
    assert not mgr.should_summarize(msgs_10)

    # 7 pairs = 14 messages (at hard threshold 14)
    msgs_14 = create_turn_pairs(7)
    assert len(msgs_14) == 14
    assert mgr.is_above_soft_threshold(msgs_14)
    assert not mgr.should_summarize(msgs_14)

    # 8 pairs = 16 messages (exceeds hard threshold 14)
    msgs_16 = create_turn_pairs(8)
    assert len(msgs_16) == 16
    assert mgr.is_above_soft_threshold(msgs_16)
    assert mgr.should_summarize(msgs_16)


def test_split_for_summarization_below_hard_threshold():
    """No eviction occurs if message count is <= 14."""
    mgr = ConversationWindowManager()
    msgs_14 = create_turn_pairs(7)

    evicted, remaining = mgr.split_for_summarization(msgs_14)
    assert evicted == []
    assert len(remaining) == 14
    assert remaining == msgs_14


def test_split_for_summarization_above_hard_threshold():
    """First 4 messages are sliced for eviction and remaining 12 remain active."""
    mgr = ConversationWindowManager()
    msgs_16 = create_turn_pairs(8)

    evicted, remaining = mgr.split_for_summarization(msgs_16)

    # First 4 messages evicted
    assert len(evicted) == 4
    assert evicted[0].content == "User question 1"
    assert evicted[1].content == "Assistant answer 1"
    assert evicted[2].content == "User question 2"
    assert evicted[3].content == "Assistant answer 2"

    # Remaining 12 messages kept active
    assert len(remaining) == 12
    assert remaining[0].content == "User question 3"
    assert remaining[-1].content == "Assistant answer 8"


def test_render_messages():
    """Messages are rendered cleanly with role prefixes."""
    msgs = [
        HumanMessage(content="How do I get an income certificate?"),
        AIMessage(content="You need salary slips and Form 16."),
    ]
    rendered = ConversationWindowManager.render_messages(msgs)
    assert "User: How do I get an income certificate?" in rendered
    assert "Assistant: You need salary slips and Form 16." in rendered
