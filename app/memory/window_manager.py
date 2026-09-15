"""Conversation window manager for dual-threshold memory management."""

import logging
from typing import List, Tuple
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

logger = logging.getLogger(__name__)

# Threshold constants per architecture spec
SOFT_THRESHOLD_MESSAGES = 10  # 5 conversation turn pairs
HARD_THRESHOLD_MESSAGES = 14  # 7 conversation turn pairs
EVICTION_BATCH_SIZE = 4       # 2 conversation turn pairs evicted on hard threshold


class ConversationWindowManager:
    """Manages sliding message windows and eviction decisions based on dual thresholds."""

    def __init__(
        self,
        soft_threshold: int = SOFT_THRESHOLD_MESSAGES,
        hard_threshold: int = HARD_THRESHOLD_MESSAGES,
        eviction_batch_size: int = EVICTION_BATCH_SIZE,
    ):
        self.soft_threshold = soft_threshold
        self.hard_threshold = hard_threshold
        self.eviction_batch_size = eviction_batch_size

    def should_summarize(self, messages: List[BaseMessage]) -> bool:
        """Return True if message count exceeds the hard threshold."""
        return len(messages) > self.hard_threshold

    def is_above_soft_threshold(self, messages: List[BaseMessage]) -> bool:
        """Return True if message count is at or above the soft threshold."""
        return len(messages) >= self.soft_threshold

    def split_for_summarization(
        self, messages: List[BaseMessage]
    ) -> Tuple[List[BaseMessage], List[BaseMessage]]:
        """Split messages into (evicted_messages_to_summarize, remaining_active_messages).

        If the hard threshold is exceeded, the oldest eviction_batch_size (4)
        messages are sliced out for summarization, while the rest remain active.
        If threshold is not exceeded, returns ([], messages).
        """
        if not self.should_summarize(messages):
            return [], list(messages)

        evicted = list(messages[: self.eviction_batch_size])
        remaining = list(messages[self.eviction_batch_size :])
        return evicted, remaining

    @staticmethod
    def render_messages(messages: List[BaseMessage]) -> str:
        """Render a sequence of messages into a clean, human-readable transcript."""
        lines = []
        for msg in messages:
            if isinstance(msg, HumanMessage) or getattr(msg, "type", "") == "human":
                lines.append(f"User: {msg.content}")
            elif isinstance(msg, AIMessage) or getattr(msg, "type", "") == "ai":
                lines.append(f"Assistant: {msg.content}")
            elif isinstance(msg, SystemMessage) or getattr(msg, "type", "") == "system":
                lines.append(f"System: {msg.content}")
            else:
                lines.append(f"{getattr(msg, 'type', 'Message')}: {msg.content}")
        return "\n".join(lines)


__all__ = [
    "SOFT_THRESHOLD_MESSAGES",
    "HARD_THRESHOLD_MESSAGES",
    "EVICTION_BATCH_SIZE",
    "ConversationWindowManager",
]
