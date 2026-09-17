"""Langfuse integration helpers with safe no-op fallback."""

from collections.abc import Iterator
from contextlib import contextmanager
from functools import cache
import logging
import sys
from typing import Any, Optional

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


class NoOpObservation:
    """Observation object used when Langfuse is disabled or unavailable."""

    def update(self, **kwargs: Any) -> None:
        return None


@cache
def get_langfuse_client() -> Optional[Any]:
    """Build and cache the Langfuse client when tracing is enabled."""

    settings = get_settings()
    if not _can_enable_langfuse(settings):
        return None

    try:
        from langfuse import Langfuse
    except Exception as exc:
        logger.warning("Langfuse SDK is unavailable; observability is disabled: %s", exc)
        return None

    try:
        return Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            base_url=settings.langfuse_base_url,
        )
    except Exception as exc:
        logger.warning("Failed to initialize Langfuse client; observability is disabled: %s", exc)
        return None


@contextmanager
def start_observation(
    name: str,
    *,
    as_type: str = "span",
    input: Optional[dict[str, Any]] = None,
    output: Optional[dict[str, Any]] = None,
    metadata: Optional[dict[str, Any]] = None,
    model: Optional[str] = None,
    usage_details: Optional[dict[str, int]] = None,
    cost_details: Optional[dict[str, float]] = None,
) -> Iterator[Any]:
    """Start a Langfuse observation or yield a no-op observation.

    Application exceptions raised inside the context are always re-raised. Only
    observability setup/finalization failures are isolated from the request path.
    """

    client = get_langfuse_client()
    if client is None:
        observation = NoOpObservation()
        if output is not None:
            observation.update(output=output)
        yield observation
        return

    kwargs: dict[str, Any] = {"name": name, "as_type": as_type}
    if input is not None:
        kwargs["input"] = input
    if output is not None:
        kwargs["output"] = output
    if metadata is not None:
        kwargs["metadata"] = metadata
    if model is not None:
        kwargs["model"] = model
    if usage_details is not None:
        kwargs["usage_details"] = usage_details
    if cost_details is not None:
        kwargs["cost_details"] = cost_details

    try:
        manager = client.start_as_current_observation(**kwargs)
        observation = manager.__enter__()
    except Exception as exc:
        logger.warning("Failed to start Langfuse observation '%s': %s", name, exc)
        yield NoOpObservation()
        return

    try:
        yield observation
    except Exception:
        exc_info = sys.exc_info()
        _safe_update(observation, level="ERROR")
        _safe_exit(manager, *exc_info)
        raise
    else:
        _safe_exit(manager, None, None, None)


def _can_enable_langfuse(settings: Settings) -> bool:
    return bool(
        settings.langfuse_enabled
        and settings.langfuse_public_key
        and settings.langfuse_secret_key
    )


def flush_langfuse() -> None:
    """Flush queued Langfuse events when the SDK is enabled."""

    client = get_langfuse_client()
    if client is None or not hasattr(client, "flush"):
        return
    try:
        client.flush()
    except Exception as exc:
        logger.warning("Failed to flush Langfuse observations: %s", exc)


def _safe_update(observation: Any, **kwargs: Any) -> None:
    try:
        observation.update(**kwargs)
    except Exception as exc:
        logger.warning("Failed to update Langfuse observation: %s", exc)


def _safe_exit(manager: Any, exc_type: Any, exc: Any, traceback: Any) -> None:
    try:
        manager.__exit__(exc_type, exc, traceback)
    except Exception as exit_exc:
        logger.warning("Failed to close Langfuse observation: %s", exit_exc)


__all__ = [
    "NoOpObservation",
    "flush_langfuse",
    "get_langfuse_client",
    "start_observation",
]
