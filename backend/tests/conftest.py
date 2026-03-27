"""Shared pytest fixtures for the AI Coding Pipeline test suite."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.database import Base, get_db
from app.main import create_app
from app.models.project import Project
from app.models.ticket import ColumnName, Priority, Ticket
from app.models.user import User
from app.services.auth_service import create_access_token, hash_password

# ---------------------------------------------------------------------------
# Test database — uses SQLite for fast, isolated tests
# ---------------------------------------------------------------------------

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# ---------------------------------------------------------------------------
# Event-loop fixture
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def event_loop():
    """Create a single event loop for the entire test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ---------------------------------------------------------------------------
# Database setup / teardown
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async session backed by an in-memory SQLite database.

    Tables are created before each test and dropped after, ensuring full
    isolation between test cases.
    """
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with TestSessionLocal() as session:
        yield session

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


# ---------------------------------------------------------------------------
# FastAPI test client
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="function")
async def async_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Yield an ``httpx.AsyncClient`` wired to the FastAPI app.

    The app's ``get_db`` dependency is overridden to use the test session,
    so every request shares the same in-memory database.
    """
    app = create_app()

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Entity factory fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def create_test_user(db_session: AsyncSession):
    """Factory fixture that creates and returns a ``User``."""

    async def _create(
        email: str = "testuser@example.com",
        password: str = "securepassword123",  # noqa: S107
        full_name: str = "Test User",
        role: str = "owner",
    ) -> User:
        user = User(
            id=uuid.uuid4(),
            email=email,
            hashed_password=hash_password(password),
            full_name=full_name,
            role=role,
            is_active=True,
        )
        db_session.add(user)
        await db_session.flush()
        await db_session.refresh(user)
        return user

    return _create


@pytest_asyncio.fixture
async def create_test_project(db_session: AsyncSession, create_test_user):
    """Factory fixture that creates and returns a ``Project``."""

    async def _create(
        name: str = "Test Project",
        slug: str = "test-project",
        creator: User | None = None,
    ) -> Project:
        if creator is None:
            creator = await create_test_user()
        project = Project(
            id=uuid.uuid4(),
            name=name,
            slug=slug,
            description="A test project",
            created_by=creator.id,
        )
        db_session.add(project)
        await db_session.flush()
        await db_session.refresh(project)
        return project

    return _create


@pytest_asyncio.fixture
async def create_test_ticket(db_session: AsyncSession, create_test_project):
    """Factory fixture that creates and returns a ``Ticket``."""

    async def _create(
        project: Project | None = None,
        title: str = "Test Ticket",
        column: str = "backlog",
        priority: str = "P2",
        description: str = "A test ticket description",
    ) -> Ticket:
        if project is None:
            project = await create_test_project()
        ticket = Ticket(
            id=uuid.uuid4(),
            project_id=project.id,
            ticket_number=1,
            title=title,
            description=description,
            column_name=ColumnName(column),
            priority=Priority(priority),
        )
        db_session.add(ticket)
        await db_session.flush()
        await db_session.refresh(ticket)
        return ticket

    return _create


@pytest_asyncio.fixture
async def auth_headers(create_test_user) -> dict[str, str]:
    """Return ``Authorization`` headers with a valid JWT for a test user."""
    user = await create_test_user()
    token = create_access_token(user.id, user.role)
    return {"Authorization": f"Bearer {token}"}
