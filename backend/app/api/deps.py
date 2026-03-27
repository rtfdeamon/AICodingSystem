"""Shared FastAPI dependencies for authentication and authorisation."""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.user import User

_bearer_scheme = HTTPBearer(auto_error=True)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Decode the JWT from the ``Authorization`` header and return the
    corresponding :class:`User`.

    Raises ``401`` if the token is invalid/expired or the user is not found.
    """
    token = credentials.credentials
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
        )
        sub: str | None = payload.get("sub")
        if sub is None:
            raise credentials_exception
        user_id = uuid.UUID(sub)
    except (JWTError, ValueError) as exc:
        raise credentials_exception from exc

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise credentials_exception
    return user


def require_role(*allowed_roles: str) -> Any:
    """Return a dependency that ensures the current user has one of the
    specified roles.

    Usage::

        @router.get("/admin", dependencies=[Depends(require_role("owner"))])
        async def admin_endpoint(): ...
    """

    async def _role_checker(
        current_user: Annotated[User, Depends(get_current_user)],
    ) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{current_user.role}' is not permitted. "
                f"Required: {', '.join(allowed_roles)}.",
            )
        return current_user

    return _role_checker
