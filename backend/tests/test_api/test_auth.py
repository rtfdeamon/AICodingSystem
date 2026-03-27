"""Tests for authentication endpoints: register, login, refresh, me."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def test_register_success(async_client: AsyncClient) -> None:
    """Registering with a fresh email returns 201 and tokens."""
    resp = await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": "newuser@example.com",
            "password": "strongpassword123",
            "full_name": "New User",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert "access_token" in body
    assert "refresh_token" in body
    assert body["token_type"] == "bearer"
    assert body["expires_in"] > 0


async def test_register_duplicate_email(async_client: AsyncClient) -> None:
    """Registering the same email twice returns 409 Conflict."""
    payload = {
        "email": "dupe@example.com",
        "password": "strongpassword123",
        "full_name": "First User",
    }
    resp1 = await async_client.post("/api/v1/auth/register", json=payload)
    assert resp1.status_code == 201

    resp2 = await async_client.post("/api/v1/auth/register", json=payload)
    assert resp2.status_code == 409
    assert "already exists" in resp2.json()["detail"].lower()


async def test_login_success(async_client: AsyncClient) -> None:
    """Logging in with correct credentials returns tokens."""
    # Register first
    await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": "login@example.com",
            "password": "strongpassword123",
            "full_name": "Login User",
        },
    )

    resp = await async_client.post(
        "/api/v1/auth/login",
        json={
            "email": "login@example.com",
            "password": "strongpassword123",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert "refresh_token" in body


async def test_login_wrong_password(async_client: AsyncClient) -> None:
    """Logging in with wrong password returns 401."""
    await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": "wrongpw@example.com",
            "password": "strongpassword123",
            "full_name": "Wrong PW User",
        },
    )

    resp = await async_client.post(
        "/api/v1/auth/login",
        json={
            "email": "wrongpw@example.com",
            "password": "totallyWrongPassword",
        },
    )
    assert resp.status_code == 401


async def test_refresh_token(async_client: AsyncClient) -> None:
    """Exchanging a valid refresh token yields new tokens."""
    reg = await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": "refresh@example.com",
            "password": "strongpassword123",
            "full_name": "Refresh User",
        },
    )
    refresh_token = reg.json()["refresh_token"]

    resp = await async_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert "refresh_token" in body


async def test_get_me(async_client: AsyncClient) -> None:
    """The /me endpoint returns the authenticated user's profile."""
    reg = await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": "me@example.com",
            "password": "strongpassword123",
            "full_name": "Me User",
        },
    )
    token = reg.json()["access_token"]

    resp = await async_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == "me@example.com"
    assert body["full_name"] == "Me User"
