"""Authentication service: password hashing, JWT creation, user registration/login."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import bcrypt
from fastapi import HTTPException, status
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.user import User
from app.schemas.auth import RegisterRequest, TokenResponse

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Password helpers
# ---------------------------------------------------------------------------


def hash_password(password: str) -> str:
    """Return a bcrypt hash of *password*."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Return ``True`` if *plain_password* matches *hashed_password*."""
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------


def create_access_token(user_id: uuid.UUID, role: str) -> str:
    """Create a short-lived access token containing the user id and role."""
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "role": role,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.JWT_EXPIRE_MINUTES),
    }
    return cast(str, jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM))


def create_refresh_token(user_id: uuid.UUID) -> str:
    """Create a long-lived refresh token (7-day default)."""
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "iat": now,
        "exp": now + timedelta(days=settings.JWT_REFRESH_EXPIRE_DAYS),
    }
    return cast(str, jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM))


def decode_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT.  Raises :class:`HTTPException` on failure."""
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
        )
        return payload
    except JWTError as exc:
        logger.warning("JWT decode failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def _build_token_response(user: User) -> TokenResponse:
    """Build a :class:`TokenResponse` for the given user."""
    access = create_access_token(user.id, user.role)
    refresh = create_refresh_token(user.id)
    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        expires_in=settings.JWT_EXPIRE_MINUTES * 60,
    )


# ---------------------------------------------------------------------------
# Registration / authentication
# ---------------------------------------------------------------------------


async def register_user(db: AsyncSession, data: RegisterRequest) -> tuple[User, TokenResponse]:
    """Create a new user and return the user with JWT tokens.

    Raises 409 if the email is already taken.
    """
    existing = await db.execute(select(User).where(User.email == data.email))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists.",
        )

    user = User(
        email=data.email,
        hashed_password=hash_password(data.password),
        full_name=data.full_name,
        role="owner",
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)

    logger.info("User registered: %s (id=%s)", user.email, user.id)
    tokens = _build_token_response(user)
    return user, tokens


async def authenticate_user(db: AsyncSession, email: str, password: str) -> TokenResponse:
    """Verify email/password credentials and return JWT tokens.

    Raises 401 on invalid credentials.
    """
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid email or password.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise credentials_exc

    if user.hashed_password is None or not verify_password(password, user.hashed_password):
        raise credentials_exc

    logger.info("User authenticated: %s (id=%s)", user.email, user.id)
    return _build_token_response(user)
