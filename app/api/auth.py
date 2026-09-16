"""Supabase Authentication dependency for FastAPI."""

from dataclasses import dataclass
import logging
import os
from typing import Optional

from fastapi import Depends, Header, HTTPException, status
import jwt

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AuthenticatedUser:
    """Authenticated citizen extracted from validated Supabase JWT."""

    id: str
    email: Optional[str] = None
    role: str = "authenticated"


def get_optional_user(
    authorization: Optional[str] = Header(None),
) -> Optional[AuthenticatedUser]:
    """Extract authenticated user from Authorization Bearer header, or None for guests."""
    if not authorization:
        return None

    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header must start with 'Bearer '",
        )

    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token missing from Authorization header",
        )

    # 1. Primary: Verify directly with live Supabase Auth API if client is connected
    try:
        from app.memory.repository import get_default_memory_repository

        repo = get_default_memory_repository()
        if repo._client is not None and repo.is_live:
            user_res = repo._client.auth.get_user(token)
            if user_res and getattr(user_res, "user", None):
                u = user_res.user
                return AuthenticatedUser(
                    id=str(u.id),
                    email=getattr(u, "email", None),
                    role=getattr(u, "role", "authenticated"),
                )
    except Exception as exc:
        logger.debug("Live Supabase client auth verification did not succeed: %s", exc)

    # 2. Secondary: Verify with local SUPABASE_JWT_SECRET if configured
    jwt_secret = os.getenv("SUPABASE_JWT_SECRET")
    if jwt_secret:
        try:
            payload = jwt.decode(
                token,
                jwt_secret,
                algorithms=["HS256", "HS384", "HS512"],
                options={"verify_aud": False},
            )
            user_id = payload.get("sub")
            if user_id:
                return AuthenticatedUser(
                    id=str(user_id),
                    email=payload.get("email"),
                    role=payload.get("role", "authenticated"),
                )
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication token has expired",
            )
        except jwt.InvalidTokenError as exc:
            logger.debug("HMAC JWT secret verification failed: %s", exc)

    # 3. Tertiary (Development fallback): Decode payload claims without signature verification
    is_dev = os.getenv("APP_ENV", "development").lower() in ("development", "dev", "test")
    if is_dev:
        try:
            payload = jwt.decode(
                token,
                options={"verify_signature": False, "verify_aud": False},
            )
            user_id = payload.get("sub")
            if user_id:
                logger.info("Decoded user '%s' from token in development mode.", user_id)
                return AuthenticatedUser(
                    id=str(user_id),
                    email=payload.get("email"),
                    role=payload.get("role", "authenticated"),
                )
        except Exception as exc:
            logger.debug("Unverified JWT decode failed: %s", exc)

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired authentication token",
    )


def require_authenticated_user(
    user: Optional[AuthenticatedUser] = Depends(get_optional_user),
) -> AuthenticatedUser:
    """Enforce authentication for user-specific endpoints like thread listing."""
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )
    return user


__all__ = [
    "AuthenticatedUser",
    "get_optional_user",
    "require_authenticated_user",
]
