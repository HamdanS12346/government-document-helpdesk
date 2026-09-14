"""Safe public serialization helpers for API payloads."""

from typing import Any

from app.contracts.chat import ChatMessage


def serialize_public_message(message: Any) -> ChatMessage | None:
    """Serialize a LangChain or dict message to public role/content only."""

    role = _message_role(message)
    content = _message_content(message)
    if role is None or content is None:
        return None
    return ChatMessage(role=role, content=content)


def _message_role(message: Any) -> str | None:
    if isinstance(message, dict):
        role = message.get("role") or message.get("type")
    else:
        role = getattr(message, "role", None) or getattr(message, "type", None)

    if role in {"assistant", "ai"}:
        return "assistant"
    if role in {"user", "human"}:
        return "user"
    return None


def _message_content(message: Any) -> str | None:
    if isinstance(message, dict):
        content = message.get("content")
    else:
        content = getattr(message, "content", None)

    if not isinstance(content, str):
        return None
    if not content.strip():
        return None
    return content


__all__ = ["serialize_public_message"]
