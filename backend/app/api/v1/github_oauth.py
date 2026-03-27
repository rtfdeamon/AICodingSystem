"""GitHub OAuth authentication endpoints."""

from __future__ import annotations

import logging
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.user import User
from app.schemas.auth import TokenResponse
from app.services.auth_service import (
    create_access_token,
    create_refresh_token,
)

logger = logging.getLogger(__name__)

router = APIRouter()


class GitHubCallbackRequest(BaseModel):
    code: str


class GitHubAuthUrl(BaseModel):
    url: str


@router.get("/github/url", response_model=GitHubAuthUrl)
async def github_auth_url() -> GitHubAuthUrl:
    """Return the GitHub OAuth authorization URL."""
    if not settings.GITHUB_CLIENT_ID:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="GitHub OAuth not configured. Set GITHUB_CLIENT_ID.",
        )
    url = (
        f"https://github.com/login/oauth/authorize"
        f"?client_id={settings.GITHUB_CLIENT_ID}"
        f"&scope=user:email,repo"
    )
    return GitHubAuthUrl(url=url)


@router.post("/github/callback", response_model=TokenResponse)
async def github_callback(
    data: GitHubCallbackRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    """Exchange a GitHub OAuth code for JWT tokens.

    Creates a new user if this is the first login with this GitHub account.
    """
    if not settings.GITHUB_CLIENT_ID or not settings.GITHUB_CLIENT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="GitHub OAuth not configured.",
        )

    # Exchange code for access token
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            "https://github.com/login/oauth/access_token",
            json={
                "client_id": settings.GITHUB_CLIENT_ID,
                "client_secret": settings.GITHUB_CLIENT_SECRET,
                "code": data.code,
            },
            headers={"Accept": "application/json"},
        )

    if token_resp.status_code != 200:
        raise HTTPException(status_code=400, detail="Failed to exchange code for token")

    token_data = token_resp.json()
    gh_access_token = token_data.get("access_token")
    if not gh_access_token:
        raise HTTPException(
            status_code=400,
            detail=token_data.get("error_description", "OAuth failed"),
        )

    # Get user info from GitHub
    async with httpx.AsyncClient() as client:
        user_resp = await client.get(
            "https://api.github.com/user",
            headers={"Authorization": f"Bearer {gh_access_token}"},
        )
        emails_resp = await client.get(
            "https://api.github.com/user/emails",
            headers={"Authorization": f"Bearer {gh_access_token}"},
        )

    if user_resp.status_code != 200:
        raise HTTPException(status_code=400, detail="Failed to fetch GitHub user")

    gh_user = user_resp.json()
    gh_id = str(gh_user["id"])
    gh_name = gh_user.get("name") or gh_user.get("login", "GitHub User")
    gh_avatar = gh_user.get("avatar_url")

    # Find primary email
    email = None
    if emails_resp.status_code == 200:
        for e in emails_resp.json():
            if e.get("primary") and e.get("verified"):
                email = e["email"]
                break
    if not email:
        email = gh_user.get("email")
    if not email:
        raise HTTPException(status_code=400, detail="No verified email found on GitHub")

    # Find or create user
    result = await db.execute(select(User).where(User.github_id == gh_id))
    user = result.scalar_one_or_none()

    if user is None:
        # Check if email already exists
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        if user:
            # Link GitHub to existing account
            user.github_id = gh_id
            user.oauth_provider = "github"
            if not user.avatar_url:
                user.avatar_url = gh_avatar
        else:
            # Create new user
            user = User(
                email=email,
                full_name=gh_name,
                github_id=gh_id,
                oauth_provider="github",
                avatar_url=gh_avatar,
                role="developer",
            )
            db.add(user)

    await db.flush()
    await db.refresh(user)

    logger.info("GitHub OAuth login: %s (github_id=%s)", user.email, gh_id)

    access = create_access_token(user.id, user.role)
    refresh = create_refresh_token(user.id)
    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        expires_in=settings.JWT_EXPIRE_MINUTES * 60,
    )
