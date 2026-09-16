"""Unit and integration tests for authentication dependency and thread endpoints."""

import datetime
from fastapi import status
from fastapi.testclient import TestClient
import jwt
import pytest

from app.api.auth import AuthenticatedUser, get_optional_user, require_authenticated_user
from app.api.main import app
from app.memory.repository import SupabaseMemoryRepository, set_default_memory_repository
from langchain_core.messages import AIMessage, HumanMessage

TEST_JWT_SECRET = "super-secret-test-jwt-key-32-chars-long"


@pytest.fixture
def repo(monkeypatch):
    """Provide clean in-memory repository for isolated tests."""
    in_memory_repo = SupabaseMemoryRepository(client=None)
    set_default_memory_repository(in_memory_repo)
    return in_memory_repo


@pytest.fixture
def test_user_token(monkeypatch):
    """Generate a valid signed Supabase JWT for user-123."""
    monkeypatch.setenv("SUPABASE_JWT_SECRET", TEST_JWT_SECRET)
    payload = {
        "sub": "user-123-abc",
        "email": "citizen@example.gov.in",
        "role": "authenticated",
        "exp": datetime.datetime.now(datetime.timezone.utc).timestamp() + 3600,
    }
    return jwt.encode(payload, TEST_JWT_SECRET, algorithm="HS256")


@pytest.fixture
def other_user_token(monkeypatch):
    """Generate a valid signed Supabase JWT for user-456."""
    monkeypatch.setenv("SUPABASE_JWT_SECRET", TEST_JWT_SECRET)
    payload = {
        "sub": "user-456-def",
        "email": "other@example.gov.in",
        "role": "authenticated",
        "exp": datetime.datetime.now(datetime.timezone.utc).timestamp() + 3600,
    }
    return jwt.encode(payload, TEST_JWT_SECRET, algorithm="HS256")


def test_get_optional_user_guest():
    """Verify missing authorization returns None without raising."""
    assert get_optional_user(authorization=None) is None
    assert get_optional_user(authorization="") is None


def test_get_optional_user_invalid_header():
    """Verify malformed authorization headers raise 401."""
    with pytest.raises(Exception) as exc_info:
        get_optional_user(authorization="Basic 12345")
    assert "Authorization header must start with 'Bearer '" in str(exc_info.value.detail)


def test_get_optional_user_valid_jwt(test_user_token):
    """Verify valid JWT extracts AuthenticatedUser."""
    user = get_optional_user(authorization=f"Bearer {test_user_token}")
    assert user is not None
    assert user.id == "user-123-abc"
    assert user.email == "citizen@example.gov.in"
    assert user.role == "authenticated"


def test_require_authenticated_user_unauthorized():
    """Verify require_authenticated_user raises 401 when user is None."""
    with pytest.raises(Exception) as exc_info:
        require_authenticated_user(user=None)
    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED


def test_get_threads_unauthenticated(repo):
    """GET /threads should reject unauthenticated requests with 401."""
    client = TestClient(app)
    response = client.get("/threads")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_get_threads_authenticated_isolation(repo, test_user_token, other_user_token):
    """GET /threads should return only the threads belonging to the requesting user."""
    # Seed threads
    t1 = repo.get_or_create_thread(thread_id="t-1", title="Passport Query", user_id="user-123-abc")
    t2 = repo.get_or_create_thread(thread_id="t-2", title="Driving Licence", user_id="user-456-def")
    t_guest = repo.get_or_create_thread(thread_id="t-guest", title="Anonymous Query", user_id=None)

    client = TestClient(app)

    # Request as user-123
    resp = client.get(
        "/threads",
        headers={"Authorization": f"Bearer {test_user_token}"},
    )
    assert resp.status_code == status.HTTP_200_OK
    threads = resp.json()
    assert len(threads) == 1
    assert threads[0]["id"] == "t-1"
    assert threads[0]["title"] == "Passport Query"

    # Request as user-456
    resp2 = client.get(
        "/threads",
        headers={"Authorization": f"Bearer {other_user_token}"},
    )
    assert resp2.status_code == status.HTTP_200_OK
    threads2 = resp2.json()
    assert len(threads2) == 1
    assert threads2[0]["id"] == "t-2"


def test_get_thread_messages_ownership(repo, test_user_token, other_user_token):
    """GET /threads/{id}/messages should allow owner and forbid other users."""
    repo.get_or_create_thread(thread_id="t-private", title="Private Tax Query", user_id="user-123-abc")
    repo.append_turn(
        thread_id="t-private",
        human_message=HumanMessage(content="How do I file ITR?"),
        ai_message=AIMessage(content="Use the Income Tax e-filing portal."),
    )

    client = TestClient(app)

    # Other user cannot view messages
    forbidden_resp = client.get(
        "/threads/t-private/messages",
        headers={"Authorization": f"Bearer {other_user_token}"},
    )
    assert forbidden_resp.status_code == status.HTTP_403_FORBIDDEN

    # Owner can view messages
    ok_resp = client.get(
        "/threads/t-private/messages",
        headers={"Authorization": f"Bearer {test_user_token}"},
    )
    assert ok_resp.status_code == status.HTTP_200_OK
    messages = ok_resp.json()
    assert len(messages) == 2
    assert messages[0]["content"] == "How do I file ITR?"
    assert messages[1]["content"] == "Use the Income Tax e-filing portal."


def test_delete_thread(repo, test_user_token, other_user_token):
    """DELETE /threads/{id} should only allow the owner to delete their thread."""
    repo.get_or_create_thread(thread_id="t-del", title="Delete Me", user_id="user-123-abc")

    client = TestClient(app)

    # Non-owner cannot delete
    forbidden_resp = client.delete(
        "/threads/t-del",
        headers={"Authorization": f"Bearer {other_user_token}"},
    )
    assert forbidden_resp.status_code == status.HTTP_403_FORBIDDEN

    # Owner can delete
    ok_resp = client.delete(
        "/threads/t-del",
        headers={"Authorization": f"Bearer {test_user_token}"},
    )
    assert ok_resp.status_code == status.HTTP_200_OK
    assert ok_resp.json()["success"] is True

    # After deletion, thread is gone
    assert repo.get_thread("t-del") is None
