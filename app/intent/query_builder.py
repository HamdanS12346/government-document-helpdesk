"""Build the bounded query supplied to the intent classifier."""

from collections.abc import Iterable
from typing import Any

from app.contracts.normalized_input import NormalizedInput


MAX_PREVIEW_LENGTH = 4_000
MAX_MESSAGE_COUNT = 10


def _render(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _render_items(items: Iterable[Any], label: str) -> list[str]:
    rendered = []
    for index, item in enumerate(items, start=1):
        preview = _render(item)[:MAX_PREVIEW_LENGTH]
        if preview:
            rendered.append(f"{label} {index}:\n{preview}")
    return rendered


def _render_messages(messages: Iterable[Any]) -> list[str]:
    rendered = []
    for message in list(messages)[-MAX_MESSAGE_COUNT:]:
        if isinstance(message, dict):
            role = _render(message.get("role")) or "message"
            content = _render(message.get("content"))
        else:
            role = _render(getattr(message, "type", None)) or "message"
            content = _render(getattr(message, "content", message))
        if content:
            rendered.append(f"{role}: {content}")
    return rendered


def build_classification_query(
    normalized_input: NormalizedInput,
    messages: Iterable[Any] | None = None,
    conversation_summary: str | None = None,
) -> str:
    """Build a deterministic, bounded classification query."""

    sections = [f"User Query:\n{normalized_input.user_query.strip()}"]
    context = _render(normalized_input.context)
    if context:
        sections.append(f"Normalized Context:\n{context}")

    sections.extend(_render_items(normalized_input.image_preview, "Image Preview"))
    sections.extend(_render_items(normalized_input.pdf_preview, "PDF Preview"))

    recent_messages = _render_messages(messages or [])
    if recent_messages:
        sections.append("Recent Conversation:\n" + "\n".join(recent_messages))

    summary = _render(conversation_summary)
    if summary:
        sections.append(f"Older Conversation Summary:\n{summary}")

    return "\n\n".join(sections)
