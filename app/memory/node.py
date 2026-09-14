"""LangGraph nodes and lifecycle hooks for conversation memory."""

import logging
from typing import Any, Dict, List, Optional
import uuid
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from app.contracts.memory import ConversationThread
from app.contracts.normalized_input import NormalizedInput
from app.graph.state import State
from app.memory.repository import SupabaseMemoryRepository, get_default_memory_repository
from app.memory.summarizer import ConversationSummarizer
from app.memory.window_manager import ConversationWindowManager

logger = logging.getLogger(__name__)

# Server-level active session thread ID (resets on server restart)
_ACTIVE_SERVER_SESSION_THREAD_ID: str = str(uuid.uuid4())


def get_server_session_thread_id() -> str:
    """Return current server runtime session thread ID."""
    global _ACTIVE_SERVER_SESSION_THREAD_ID
    return _ACTIVE_SERVER_SESSION_THREAD_ID


def reset_server_session_thread_id() -> str:
    """Reset the server session thread ID (generates clean slate)."""
    global _ACTIVE_SERVER_SESSION_THREAD_ID
    _ACTIVE_SERVER_SESSION_THREAD_ID = str(uuid.uuid4())
    return _ACTIVE_SERVER_SESSION_THREAD_ID


def resolve_thread_id(
    config: Optional[Dict[str, Any]] = None,
    state: Optional[Dict[str, Any]] = None,
    explicit_thread_id: Optional[str] = None,
) -> str:
    """Resolve active thread ID from config, state, or server default.

    Precedence:
    1. Explicit thread_id argument
    2. config["configurable"]["thread_id"]
    3. state["thread_id"]
    4. Active server session thread ID
    """
    if explicit_thread_id:
        return explicit_thread_id

    if config and isinstance(config, dict):
        cfg_id = config.get("configurable", {}).get("thread_id")
        if cfg_id:
            return str(cfg_id)

    if state and isinstance(state, dict):
        state_id = state.get("thread_id")
        if state_id:
            return str(state_id)

    return get_server_session_thread_id()


class MemoryManager:
    """Coordinates memory loading, per-turn persistence, and 10/14 rolling summarization."""

    def __init__(
        self,
        repository: Optional[SupabaseMemoryRepository] = None,
        window_manager: Optional[ConversationWindowManager] = None,
        summarizer: Optional[ConversationSummarizer] = None,
    ):
        self.repository = repository or get_default_memory_repository()
        self.window_manager = window_manager or ConversationWindowManager()
        self.summarizer = summarizer or ConversationSummarizer()

    def load_memory(
        self,
        state: State,
        config: Optional[Dict[str, Any]] = None,
        thread_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Load active context window and conversation summary from repository into state."""
        tid = resolve_thread_id(config=config, state=state, explicit_thread_id=thread_id)
        active_messages, summary, watermark = self.repository.load_active_messages(tid)

        logger.info(
            "Loaded memory for thread '%s': %d active messages, watermark=%d, has_summary=%s",
            tid,
            len(active_messages),
            watermark,
            bool(summary),
        )

        return {
            "messages": active_messages,
            "conversation_summary": summary,
        }

    def save_turn(
        self,
        state: State,
        config: Optional[Dict[str, Any]] = None,
        thread_id: Optional[str] = None,
        human_content: Optional[str] = None,
        ai_content: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Save dialogue turn, evaluate 14-message hard threshold, and condense summary if needed."""
        tid = resolve_thread_id(config=config, state=state, explicit_thread_id=thread_id)

        # 1. Resolve canonical HumanMessage (preferring rewritten/optimized query)
        if not human_content:
            raw_norm = state.get("normalized_input")
            if isinstance(raw_norm, NormalizedInput):
                human_content = raw_norm.user_query
            elif isinstance(raw_norm, dict):
                human_content = raw_norm.get("user_query", "")
            else:
                human_content = str(raw_norm or "")

        # 2. Resolve AIMessage (from state response or latest AIMessage)
        if not ai_content:
            ai_content = str(state.get("response") or "")
            if not ai_content:
                # Check messages for latest AIMessage
                for msg in reversed(state.get("messages", [])):
                    if isinstance(msg, AIMessage) or getattr(msg, "type", "") == "ai":
                        ai_content = str(msg.content)
                        break

        human_msg = HumanMessage(content=human_content or "User Query")
        ai_msg = AIMessage(content=ai_content or "Response")

        # 3. Append turn pair to repository
        self.repository.append_turn(tid, human_msg, ai_msg)

        # 4. Fetch updated active messages and evaluate thresholds
        active_messages, summary, watermark = self.repository.load_active_messages(tid)

        if self.window_manager.should_summarize(active_messages):
            logger.info(
                "Active messages (%d) exceeded hard threshold (%d) for thread '%s'; triggering summarizer.",
                len(active_messages),
                self.window_manager.hard_threshold,
                tid,
            )
            evicted, remaining = self.window_manager.split_for_summarization(active_messages)

            # Summarize the 4 oldest messages and fold into summary
            new_summary = self.summarizer.summarize(
                messages_to_summarize=evicted,
                existing_summary=summary,
            )

            # Advance watermark by the number of evicted messages (4)
            new_watermark = watermark + len(evicted)
            self.repository.update_summary_watermark(
                thread_id=tid,
                new_summary=new_summary,
                new_watermark=new_watermark,
            )

            logger.info(
                "Summarization complete for thread '%s'. New watermark=%d, active messages count=%d",
                tid,
                new_watermark,
                len(remaining),
            )

            return {
                "messages": remaining,
                "conversation_summary": new_summary,
            }

        return {
            "messages": active_messages,
            "conversation_summary": summary,
        }


# Default singleton manager instance
_default_memory_manager: Optional[MemoryManager] = None


def get_default_memory_manager() -> MemoryManager:
    """Return the shared default MemoryManager instance."""
    global _default_memory_manager
    if _default_memory_manager is None:
        _default_memory_manager = MemoryManager()
    return _default_memory_manager


def set_default_memory_manager(mgr: MemoryManager) -> None:
    """Set the shared default MemoryManager instance."""
    global _default_memory_manager
    _default_memory_manager = mgr


def load_memory_node(state: State, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """LangGraph node function to load conversation memory into state."""
    mgr = get_default_memory_manager()
    return mgr.load_memory(state=state, config=config)


def save_memory_node(state: State, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """LangGraph node function to save conversation turn and handle rolling summarization."""
    mgr = get_default_memory_manager()
    return mgr.save_turn(state=state, config=config)


__all__ = [
    "get_server_session_thread_id",
    "reset_server_session_thread_id",
    "resolve_thread_id",
    "MemoryManager",
    "get_default_memory_manager",
    "set_default_memory_manager",
    "load_memory_node",
    "save_memory_node",
]
