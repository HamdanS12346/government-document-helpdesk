"""Conversation memory contract definitions."""

from datetime import datetime
from enum import StrEnum
from typing import Any, Dict, List, Optional
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, ConfigDict, Field


class MessageRole(StrEnum):
    """Supported speaker roles for conversation messages."""

    HUMAN = "human"
    AI = "ai"
    SYSTEM = "system"


class ConversationMessage(BaseModel):
    """A single dialogue turn within a conversation thread."""

    model_config = ConfigDict(extra="allow")

    id: Optional[str] = Field(default=None, description="UUID of the message record")
    thread_id: str = Field(description="UUID of the parent conversation thread")
    role: MessageRole = Field(description="Role of the message author")
    content: str = Field(description="Text content of the message")
    sequence_number: int = Field(ge=1, description="Strictly incrementing 1-based index within thread")
    created_at: Optional[datetime] = Field(default=None, description="Creation timestamp")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional context or diagnostics")

    def to_langchain(self) -> BaseMessage:
        """Convert this message into a standard LangChain BaseMessage."""
        if self.role == MessageRole.HUMAN:
            return HumanMessage(content=self.content)
        elif self.role == MessageRole.AI:
            return AIMessage(content=self.content)
        elif self.role == MessageRole.SYSTEM:
            return SystemMessage(content=self.content)
        return HumanMessage(content=self.content)

    @classmethod
    def from_langchain(
        cls,
        message: BaseMessage,
        thread_id: str,
        sequence_number: int,
        id: Optional[str] = None,
        created_at: Optional[datetime] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "ConversationMessage":
        """Construct a ConversationMessage from a LangChain BaseMessage."""
        if isinstance(message, HumanMessage) or getattr(message, "type", "") == "human":
            role = MessageRole.HUMAN
        elif isinstance(message, AIMessage) or getattr(message, "type", "") == "ai":
            role = MessageRole.AI
        elif isinstance(message, SystemMessage) or getattr(message, "type", "") == "system":
            role = MessageRole.SYSTEM
        else:
            role = MessageRole.HUMAN

        return cls(
            id=id,
            thread_id=thread_id,
            role=role,
            content=str(message.content),
            sequence_number=sequence_number,
            created_at=created_at,
            metadata=metadata or {},
        )


class ConversationThread(BaseModel):
    """State and metadata container for a conversation session thread."""

    model_config = ConfigDict(extra="allow")

    id: str = Field(description="Unique UUID identifying the conversation thread")
    user_id: Optional[str] = Field(default=None, description="Optional citizen/user identifier")
    title: Optional[str] = Field(default=None, description="Descriptive thread topic or query title")
    status: str = Field(default="active", description="Status of the thread: 'active', 'archived', 'closed'")
    conversation_summary: str = Field(default="", description="Rolling condensed summary of historical turns")
    last_summarized_seq: int = Field(
        default=0,
        ge=0,
        description="Thread-level sequence watermark: messages <= this index are folded into conversation_summary",
    )
    created_at: Optional[datetime] = Field(default=None, description="Thread creation timestamp")
    updated_at: Optional[datetime] = Field(default=None, description="Last update timestamp")


class MemorySnapshot(BaseModel):
    """Working memory state injected into and returned by LangGraph nodes."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    thread_id: str = Field(description="Active conversation thread ID")
    active_messages: List[BaseMessage] = Field(
        default_factory=list,
        description="Unsummarized active message window passed to LLM nodes",
    )
    conversation_summary: str = Field(
        default="",
        description="Condensed historical summary for earlier turns",
    )
    last_summarized_seq: int = Field(
        default=0,
        description="Current thread sequence watermark",
    )
    total_messages_count: int = Field(
        default=0,
        description="Total lifetime message count for this thread in storage",
    )


__all__ = [
    "MessageRole",
    "ConversationMessage",
    "ConversationThread",
    "MemorySnapshot",
]
