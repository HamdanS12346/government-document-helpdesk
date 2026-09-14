"""Conversation memory repository providing persistence to Supabase with in-memory fallback."""

from datetime import datetime, timezone
import logging
import os
from typing import Any, Dict, List, Optional, Tuple
import uuid
from langchain_core.messages import BaseMessage
from app.contracts.memory import (
    ConversationMessage,
    ConversationThread,
    MemorySnapshot,
    MessageRole,
)

logger = logging.getLogger(__name__)


class SupabaseMemoryRepository:
    """Repository managing conversation threads and messages in Supabase (or local fallback)."""

    def __init__(
        self,
        supabase_url: Optional[str] = None,
        supabase_key: Optional[str] = None,
        client: Optional[Any] = None,
    ):
        self.supabase_url = supabase_url or os.getenv("SUPABASE_URL")
        self.supabase_key = supabase_key or os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        self._client = client
        self._in_memory_threads: Dict[str, ConversationThread] = {}
        self._in_memory_messages: Dict[str, List[ConversationMessage]] = {}
        self._is_live_supabase = False

        self._init_client()

    def _init_client(self) -> None:
        """Initialize the Supabase client if credentials are configured."""
        if self._client is not None:
            self._is_live_supabase = True
            return

        if self.supabase_url and self.supabase_key:
            try:
                from supabase import create_client  # type: ignore

                self._client = create_client(self.supabase_url, self.supabase_key)
                self._is_live_supabase = True
                logger.info("Connected to Supabase conversation memory at %s", self.supabase_url)
            except Exception as exc:
                logger.warning(
                    "Could not initialize Supabase client (%s); operating with in-memory memory repository.",
                    exc,
                )
                self._is_live_supabase = False
        else:
            logger.info("SUPABASE_URL / SUPABASE_KEY not configured; operating in local in-memory mode.")
            self._is_live_supabase = False

    @property
    def is_live(self) -> bool:
        """Return True if currently backed by live Supabase instance."""
        return self._is_live_supabase

    def get_or_create_thread(
        self,
        thread_id: str,
        title: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> ConversationThread:
        """Fetch an existing thread or create a new one."""
        now = datetime.now(timezone.utc)

        if self._is_live_supabase and self._client:
            try:
                res = (
                    self._client.table("conversation_threads")
                    .select("*")
                    .eq("id", thread_id)
                    .limit(1)
                    .execute()
                )
                if res.data and len(res.data) > 0:
                    row = res.data[0]
                    return ConversationThread.model_validate(row)

                # Create new thread
                new_row = {
                    "id": thread_id,
                    "title": title,
                    "status": "active",
                    "conversation_summary": "",
                    "last_summarized_seq": 0,
                    "created_at": now.isoformat(),
                    "updated_at": now.isoformat(),
                }
                insert_res = self._client.table("conversation_threads").insert(new_row).execute()
                return ConversationThread.model_validate(insert_res.data[0])
            except Exception as exc:
                logger.warning("Supabase get_or_create_thread failed: %s; falling back to in-memory.", exc)

        # In-memory fallback
        if thread_id not in self._in_memory_threads:
            self._in_memory_threads[thread_id] = ConversationThread(
                id=thread_id,
                title=title,
                status="active",
                conversation_summary="",
                last_summarized_seq=0,
                created_at=now,
                updated_at=now,
            )
            self._in_memory_messages[thread_id] = []
        return self._in_memory_threads[thread_id]

    def load_active_messages(
        self, thread_id: str
    ) -> Tuple[List[BaseMessage], str, int]:
        """Load active (unsummarized) messages and summary for a thread.

        Returns:
            Tuple of (active_messages_as_langchain, conversation_summary, last_summarized_seq)
        """
        thread = self.get_or_create_thread(thread_id)
        watermark = thread.last_summarized_seq
        summary = thread.conversation_summary

        if self._is_live_supabase and self._client:
            try:
                res = (
                    self._client.table("conversation_messages")
                    .select("*")
                    .eq("thread_id", thread_id)
                    .gt("sequence_number", watermark)
                    .order("sequence_number", desc=False)
                    .execute()
                )
                active_msgs = []
                for row in res.data or []:
                    conv_msg = ConversationMessage.model_validate(row)
                    active_msgs.append(conv_msg.to_langchain())
                return active_msgs, summary, watermark
            except Exception as exc:
                logger.warning("Supabase load_active_messages failed: %s; falling back to in-memory.", exc)

        # In-memory fallback
        all_msgs = self._in_memory_messages.get(thread_id, [])
        active_msgs = [
            m.to_langchain()
            for m in all_msgs
            if m.sequence_number > watermark
        ]
        return active_msgs, summary, watermark

    def get_max_sequence_number(self, thread_id: str) -> int:
        """Fetch current highest sequence number for a thread."""
        if self._is_live_supabase and self._client:
            try:
                res = (
                    self._client.table("conversation_messages")
                    .select("sequence_number")
                    .eq("thread_id", thread_id)
                    .order("sequence_number", desc=True)
                    .limit(1)
                    .execute()
                )
                if res.data and len(res.data) > 0:
                    return int(res.data[0]["sequence_number"])
                return 0
            except Exception as exc:
                logger.warning("Supabase get_max_sequence_number failed: %s; using in-memory.", exc)

        msgs = self._in_memory_messages.get(thread_id, [])
        return msgs[-1].sequence_number if msgs else 0

    def append_turn(
        self,
        thread_id: str,
        human_message: BaseMessage,
        ai_message: BaseMessage,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Tuple[ConversationMessage, ConversationMessage]:
        """Atomically append a user query and assistant response turn pair."""
        # Ensure thread exists
        self.get_or_create_thread(thread_id)

        last_seq = self.get_max_sequence_number(thread_id)
        now = datetime.now(timezone.utc)
        meta = metadata or {}

        user_seq = last_seq + 1
        ai_seq = last_seq + 2

        conv_user = ConversationMessage.from_langchain(
            message=human_message,
            thread_id=thread_id,
            sequence_number=user_seq,
            id=str(uuid.uuid4()),
            created_at=now,
            metadata=meta.get("human", {}),
        )
        conv_ai = ConversationMessage.from_langchain(
            message=ai_message,
            thread_id=thread_id,
            sequence_number=ai_seq,
            id=str(uuid.uuid4()),
            created_at=now,
            metadata=meta.get("ai", {}),
        )

        if self._is_live_supabase and self._client:
            try:
                rows = [
                    {
                        "id": conv_user.id,
                        "thread_id": thread_id,
                        "role": conv_user.role.value,
                        "content": conv_user.content,
                        "sequence_number": conv_user.sequence_number,
                        "created_at": now.isoformat(),
                    },
                    {
                        "id": conv_ai.id,
                        "thread_id": thread_id,
                        "role": conv_ai.role.value,
                        "content": conv_ai.content,
                        "sequence_number": conv_ai.sequence_number,
                        "created_at": now.isoformat(),
                    },
                ]
                self._client.table("conversation_messages").insert(rows).execute()
                self._client.table("conversation_threads").update(
                    {"updated_at": now.isoformat()}
                ).eq("id", thread_id).execute()
                return conv_user, conv_ai
            except Exception as exc:
                logger.warning("Supabase append_turn failed: %s; storing in-memory.", exc)

        # In-memory storage
        if thread_id not in self._in_memory_messages:
            self._in_memory_messages[thread_id] = []
        self._in_memory_messages[thread_id].extend([conv_user, conv_ai])
        if thread_id in self._in_memory_threads:
            self._in_memory_threads[thread_id].updated_at = now

        return conv_user, conv_ai

    def update_summary_watermark(
        self,
        thread_id: str,
        new_summary: str,
        new_watermark: int,
    ) -> None:
        """Update thread conversation_summary and advance the sequence watermark."""
        now = datetime.now(timezone.utc)

        if self._is_live_supabase and self._client:
            try:
                self._client.table("conversation_threads").update(
                    {
                        "conversation_summary": new_summary,
                        "last_summarized_seq": new_watermark,
                        "updated_at": now.isoformat(),
                    }
                ).eq("id", thread_id).execute()
                return
            except Exception as exc:
                logger.warning("Supabase update_summary_watermark failed: %s; updating in-memory.", exc)

        # In-memory fallback
        if thread_id in self._in_memory_threads:
            thread = self._in_memory_threads[thread_id]
            thread.conversation_summary = new_summary
            thread.last_summarized_seq = new_watermark
            thread.updated_at = now

    def get_full_transcript(self, thread_id: str) -> List[ConversationMessage]:
        """Fetch 100% full lifetime history of messages for user UI/auditing."""
        if self._is_live_supabase and self._client:
            try:
                res = (
                    self._client.table("conversation_messages")
                    .select("*")
                    .eq("thread_id", thread_id)
                    .order("sequence_number", desc=False)
                    .execute()
                )
                return [ConversationMessage.model_validate(r) for r in res.data or []]
            except Exception as exc:
                logger.warning("Supabase get_full_transcript failed: %s; using in-memory.", exc)

        return list(self._in_memory_messages.get(thread_id, []))


# Global singleton instance
_default_repository: Optional[SupabaseMemoryRepository] = None


def get_default_memory_repository() -> SupabaseMemoryRepository:
    """Return the shared default memory repository instance."""
    global _default_repository
    if _default_repository is None:
        _default_repository = SupabaseMemoryRepository()
    return _default_repository


def set_default_memory_repository(repo: SupabaseMemoryRepository) -> None:
    """Set the shared default memory repository instance."""
    global _default_repository
    _default_repository = repo


__all__ = [
    "SupabaseMemoryRepository",
    "get_default_memory_repository",
    "set_default_memory_repository",
]
