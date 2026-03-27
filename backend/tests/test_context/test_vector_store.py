"""Tests for app.context.vector_store — pgvector adapter."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.context.vector_store import SearchResult, VectorStore


@pytest.fixture
def mock_session() -> AsyncMock:
    """Return a mocked AsyncSession."""
    session = AsyncMock()
    session.add_all = MagicMock()
    session.flush = AsyncMock()
    return session


@pytest.fixture
def store(mock_session: AsyncMock) -> VectorStore:
    return VectorStore(mock_session)


@pytest.fixture
def project_id() -> uuid.UUID:
    return uuid.uuid4()


def _make_chunks(n: int = 2, file_path: str = "src/main.py") -> list[dict]:
    return [
        {
            "file_path": file_path,
            "chunk_index": i,
            "chunk_text": f"chunk content {i}",
            "language": "python",
            "symbol_name": f"func_{i}",
            "embedding": [0.1] * 10,
            "commit_sha": "abc123",
        }
        for i in range(n)
    ]


class TestUpsertEmbeddings:
    async def test_empty_chunks_returns_zero(
        self, store: VectorStore, project_id: uuid.UUID
    ) -> None:
        result = await store.upsert_embeddings(project_id, [])
        assert result == 0

    async def test_upserts_correct_count(
        self,
        store: VectorStore,
        project_id: uuid.UUID,
        mock_session: AsyncMock,
    ) -> None:
        chunks = _make_chunks(3)
        result = await store.upsert_embeddings(project_id, chunks)
        assert result == 3
        mock_session.add_all.assert_called_once()
        mock_session.flush.assert_awaited_once()

    async def test_deletes_existing_before_insert(
        self,
        store: VectorStore,
        project_id: uuid.UUID,
        mock_session: AsyncMock,
    ) -> None:
        chunks = _make_chunks(2, "src/main.py")
        await store.upsert_embeddings(project_id, chunks)
        # execute is called for the delete statement
        mock_session.execute.assert_awaited()

    async def test_multiple_files_deletes_each(
        self,
        store: VectorStore,
        project_id: uuid.UUID,
        mock_session: AsyncMock,
    ) -> None:
        chunks = _make_chunks(1, "a.py") + _make_chunks(1, "b.py")
        await store.upsert_embeddings(project_id, chunks)
        # Should have been called at least twice (one delete per file)
        assert mock_session.execute.await_count >= 2


class TestSearch:
    async def test_search_returns_results(
        self,
        store: VectorStore,
        project_id: uuid.UUID,
        mock_session: AsyncMock,
    ) -> None:
        mock_row = MagicMock()
        mock_row.file_path = "src/main.py"
        mock_row.chunk_index = 0
        mock_row.chunk_text = "def hello(): pass"
        mock_row.language = "python"
        mock_row.symbol_name = "hello"
        mock_row.score = 0.95
        mock_row.commit_sha = "abc123"

        mock_result = MagicMock()
        mock_result.fetchall.return_value = [mock_row]
        mock_session.execute.return_value = mock_result

        results = await store.search(project_id, [0.1] * 10, top_k=5)
        assert len(results) == 1
        assert isinstance(results[0], SearchResult)
        assert results[0].file_path == "src/main.py"
        assert results[0].score == 0.95
        assert results[0].symbol_name == "hello"

    async def test_search_empty_results(
        self,
        store: VectorStore,
        project_id: uuid.UUID,
        mock_session: AsyncMock,
    ) -> None:
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_session.execute.return_value = mock_result

        results = await store.search(project_id, [0.1] * 10)
        assert results == []


class TestDeleteProjectEmbeddings:
    async def test_delete_project_embeddings(
        self,
        store: VectorStore,
        project_id: uuid.UUID,
        mock_session: AsyncMock,
    ) -> None:
        mock_result = MagicMock()
        mock_result.rowcount = 42
        mock_session.execute.return_value = mock_result

        count = await store.delete_project_embeddings(project_id)
        assert count == 42
        mock_session.execute.assert_awaited_once()


class TestDeleteFileEmbeddings:
    async def test_delete_file_embeddings(
        self,
        store: VectorStore,
        project_id: uuid.UUID,
        mock_session: AsyncMock,
    ) -> None:
        mock_result = MagicMock()
        mock_result.rowcount = 5
        mock_session.execute.return_value = mock_result

        count = await store.delete_file_embeddings(project_id, "src/main.py")
        assert count == 5
        mock_session.execute.assert_awaited_once()


class TestSearchResult:
    def test_dataclass_fields(self) -> None:
        r = SearchResult(
            file_path="a.py",
            chunk_index=0,
            chunk_text="code",
            language="python",
            symbol_name="func",
            score=0.9,
            commit_sha="abc",
        )
        assert r.file_path == "a.py"
        assert r.score == 0.9
        assert r.commit_sha == "abc"

    def test_nullable_fields(self) -> None:
        r = SearchResult(
            file_path="a.py",
            chunk_index=0,
            chunk_text="code",
            language="python",
            symbol_name=None,
            score=0.5,
            commit_sha=None,
        )
        assert r.symbol_name is None
        assert r.commit_sha is None
