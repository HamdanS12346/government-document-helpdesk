"""Shared pytest configuration."""

import pytest

from app.config import get_settings
from app.observability.langfuse import get_langfuse_client


@pytest.fixture(autouse=True)
def disable_live_langfuse(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep tests from exporting traces using a developer's local .env."""

    monkeypatch.setenv("LANGFUSE_ENABLED", "false")
    get_settings.cache_clear()
    get_langfuse_client.cache_clear()
    yield
    get_settings.cache_clear()
    get_langfuse_client.cache_clear()
