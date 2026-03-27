"""Tests for app.context.engine — context indexing and retrieval orchestrator."""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.context.code_parser import ChunkType, CodeChunk
from app.context.engine import _INDEXABLE_EXTENSIONS, _MAX_FILE_SIZE, _SKIP_DIRS, ContextEngine
from app.context.vector_store import SearchResult


@pytest.fixture
def mock_session() -> AsyncMock:
    session = AsyncMock()
    session.add_all = MagicMock()
    session.flush = AsyncMock()
    return session


@pytest.fixture
def mock_embedding_service() -> AsyncMock:
    svc = AsyncMock()
    svc.embed_texts = AsyncMock(return_value=[[0.1] * 10, [0.2] * 10])
    svc.embed_single = AsyncMock(return_value=[0.1] * 10)
    return svc


@pytest.fixture
def engine(mock_session: AsyncMock, mock_embedding_service: AsyncMock) -> ContextEngine:
    return ContextEngine(session=mock_session, embedding_service=mock_embedding_service)


@pytest.fixture
def project_id() -> uuid.UUID:
    return uuid.uuid4()


# ── Constants ────────────────────────────────────────────────────────


class TestConstants:
    def test_indexable_extensions_includes_common(self) -> None:
        for ext in (".py", ".js", ".ts", ".go", ".rs", ".java"):
            assert ext in _INDEXABLE_EXTENSIONS

    def test_skip_dirs_includes_common(self) -> None:
        for d in (".git", "node_modules", "__pycache__", ".venv"):
            assert d in _SKIP_DIRS

    def test_max_file_size(self) -> None:
        assert _MAX_FILE_SIZE == 256 * 1024


# ── index_repo ───────────────────────────────────────────────────────


class TestIndexRepo:
    async def test_index_repo_nonexistent_path_raises(
        self, engine: ContextEngine, project_id: uuid.UUID
    ) -> None:
        with pytest.raises(FileNotFoundError):
            await engine.index_repo(project_id, "/nonexistent/path")

    async def test_index_repo_success(
        self,
        engine: ContextEngine,
        project_id: uuid.UUID,
        mock_embedding_service: AsyncMock,
        tmp_path: Path,
    ) -> None:
        # Create a small Python file
        py_file = tmp_path / "hello.py"
        py_file.write_text("def greet():\n    return 'hi'\n")

        mock_store = AsyncMock()
        mock_store.delete_project_embeddings = AsyncMock()
        mock_store.upsert_embeddings = AsyncMock(return_value=1)
        engine._store = mock_store

        mock_embedding_service.embed_texts.return_value = [[0.1] * 10]

        result = await engine.index_repo(project_id, tmp_path, commit_sha="abc123")

        assert result["files_scanned"] >= 1
        assert result["commit_sha"] == "abc123"
        mock_store.delete_project_embeddings.assert_awaited_once_with(project_id)

    async def test_index_repo_skips_excluded_dirs(
        self,
        engine: ContextEngine,
        project_id: uuid.UUID,
        mock_embedding_service: AsyncMock,
        tmp_path: Path,
    ) -> None:
        # Create files in excluded directories
        node_dir = tmp_path / "node_modules"
        node_dir.mkdir()
        (node_dir / "package.json").write_text("{}")

        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        (git_dir / "config").write_text("")

        # Create one valid file
        (tmp_path / "main.py").write_text("x = 1\n")

        mock_store = AsyncMock()
        mock_store.delete_project_embeddings = AsyncMock()
        mock_store.upsert_embeddings = AsyncMock(return_value=1)
        engine._store = mock_store
        mock_embedding_service.embed_texts.return_value = [[0.1] * 10]

        result = await engine.index_repo(project_id, tmp_path)
        # Only main.py should be scanned, not files in node_modules or .git
        assert result["files_scanned"] <= 1

    async def test_index_repo_skips_large_files(
        self,
        engine: ContextEngine,
        project_id: uuid.UUID,
        mock_embedding_service: AsyncMock,
        tmp_path: Path,
    ) -> None:
        large_file = tmp_path / "big.py"
        large_file.write_text("x = 1\n" * 100000)  # > 256KB

        mock_store = AsyncMock()
        mock_store.delete_project_embeddings = AsyncMock()
        mock_store.upsert_embeddings = AsyncMock(return_value=0)
        engine._store = mock_store

        result = await engine.index_repo(project_id, tmp_path)
        assert result["files_scanned"] == 0

    async def test_index_repo_skips_non_indexable_extensions(
        self,
        engine: ContextEngine,
        project_id: uuid.UUID,
        mock_embedding_service: AsyncMock,
        tmp_path: Path,
    ) -> None:
        (tmp_path / "image.png").write_bytes(b"\x89PNG")
        (tmp_path / "binary.exe").write_bytes(b"\x00\x00")

        mock_store = AsyncMock()
        mock_store.delete_project_embeddings = AsyncMock()
        mock_store.upsert_embeddings = AsyncMock(return_value=0)
        engine._store = mock_store

        result = await engine.index_repo(project_id, tmp_path)
        assert result["files_scanned"] == 0


# ── incremental_index ────────────────────────────────────────────────


class TestIncrementalIndex:
    async def test_incremental_index_with_existing_file(
        self,
        engine: ContextEngine,
        project_id: uuid.UUID,
        mock_embedding_service: AsyncMock,
        tmp_path: Path,
    ) -> None:
        py_file = tmp_path / "module.py"
        py_file.write_text("def func():\n    pass\n")

        mock_store = AsyncMock()
        mock_store.upsert_embeddings = AsyncMock(return_value=1)
        mock_store.delete_file_embeddings = AsyncMock()
        engine._store = mock_store
        mock_embedding_service.embed_texts.return_value = [[0.1] * 10]

        result = await engine.incremental_index(
            project_id, tmp_path, ["module.py"], commit_sha="def456"
        )
        assert result["files_updated"] == 1
        assert result["commit_sha"] == "def456"

    async def test_incremental_index_deleted_file(
        self,
        engine: ContextEngine,
        project_id: uuid.UUID,
        tmp_path: Path,
    ) -> None:
        mock_store = AsyncMock()
        mock_store.delete_file_embeddings = AsyncMock()
        mock_store.upsert_embeddings = AsyncMock(return_value=0)
        engine._store = mock_store

        await engine.incremental_index(project_id, tmp_path, ["deleted_file.py"])
        mock_store.delete_file_embeddings.assert_awaited_once_with(project_id, "deleted_file.py")

    async def test_incremental_index_skips_non_indexable(
        self,
        engine: ContextEngine,
        project_id: uuid.UUID,
        tmp_path: Path,
    ) -> None:
        (tmp_path / "image.png").write_bytes(b"PNG")

        mock_store = AsyncMock()
        mock_store.upsert_embeddings = AsyncMock(return_value=0)
        engine._store = mock_store

        result = await engine.incremental_index(project_id, tmp_path, ["image.png"])
        assert result["chunks_indexed"] == 0

    async def test_incremental_index_skips_oversized(
        self,
        engine: ContextEngine,
        project_id: uuid.UUID,
        tmp_path: Path,
    ) -> None:
        big = tmp_path / "huge.py"
        big.write_text("x = 1\n" * 100000)

        mock_store = AsyncMock()
        mock_store.upsert_embeddings = AsyncMock(return_value=0)
        engine._store = mock_store

        result = await engine.incremental_index(project_id, tmp_path, ["huge.py"])
        assert result["chunks_indexed"] == 0

    async def test_incremental_index_handles_unreadable_file(
        self,
        engine: ContextEngine,
        project_id: uuid.UUID,
        tmp_path: Path,
    ) -> None:
        py_file = tmp_path / "bad.py"
        py_file.write_text("content")

        mock_store = AsyncMock()
        mock_store.upsert_embeddings = AsyncMock(return_value=0)
        engine._store = mock_store

        with patch.object(Path, "read_text", side_effect=OSError("Permission denied")):
            result = await engine.incremental_index(project_id, tmp_path, ["bad.py"])
        assert result["chunks_indexed"] == 0


# ── search ───────────────────────────────────────────────────────────


class TestSearch:
    async def test_search_returns_results(
        self,
        engine: ContextEngine,
        project_id: uuid.UUID,
        mock_embedding_service: AsyncMock,
    ) -> None:
        expected = [
            SearchResult(
                file_path="a.py",
                chunk_index=0,
                chunk_text="code",
                language="python",
                symbol_name="func",
                score=0.9,
                commit_sha=None,
            )
        ]

        mock_store = AsyncMock()
        mock_store.search = AsyncMock(return_value=expected)
        engine._store = mock_store

        results = await engine.search(project_id, "find function", top_k=5)
        assert len(results) == 1
        assert results[0].file_path == "a.py"
        mock_embedding_service.embed_single.assert_awaited_once_with("find function")

    async def test_search_empty_results(
        self,
        engine: ContextEngine,
        project_id: uuid.UUID,
    ) -> None:
        mock_store = AsyncMock()
        mock_store.search = AsyncMock(return_value=[])
        engine._store = mock_store

        results = await engine.search(project_id, "nonexistent")
        assert results == []


# ── get_context_for_ticket ───────────────────────────────────────────


class TestGetContextForTicket:
    async def test_no_results_returns_message(
        self,
        engine: ContextEngine,
        project_id: uuid.UUID,
    ) -> None:
        mock_store = AsyncMock()
        mock_store.search = AsyncMock(return_value=[])
        engine._store = mock_store

        result = await engine.get_context_for_ticket(project_id, "add login feature")
        assert "No relevant code context" in result

    async def test_formats_results_with_headers(
        self,
        engine: ContextEngine,
        project_id: uuid.UUID,
    ) -> None:
        search_results = [
            SearchResult(
                file_path="auth.py",
                chunk_index=0,
                chunk_text="def login(): pass",
                language="python",
                symbol_name="login",
                score=0.95,
                commit_sha=None,
            ),
            SearchResult(
                file_path="models.py",
                chunk_index=1,
                chunk_text="class User: pass",
                language="python",
                symbol_name=None,
                score=0.80,
                commit_sha=None,
            ),
        ]

        mock_store = AsyncMock()
        mock_store.search = AsyncMock(return_value=search_results)
        engine._store = mock_store

        result = await engine.get_context_for_ticket(
            project_id, "implement login", acceptance_criteria="must have JWT"
        )
        assert "auth.py" in result
        assert "login" in result
        assert "0.950" in result
        assert "[1]" in result
        assert "[2]" in result

    async def test_acceptance_criteria_included_in_query(
        self,
        engine: ContextEngine,
        project_id: uuid.UUID,
        mock_embedding_service: AsyncMock,
    ) -> None:
        mock_store = AsyncMock()
        mock_store.search = AsyncMock(return_value=[])
        engine._store = mock_store

        await engine.get_context_for_ticket(
            project_id,
            "add feature",
            acceptance_criteria="must pass tests",
        )
        # embed_single should have been called with combined query
        call_args = mock_embedding_service.embed_single.call_args[0][0]
        assert "add feature" in call_args
        assert "must pass tests" in call_args


# ── _embed_and_store ─────────────────────────────────────────────────


class TestEmbedAndStore:
    async def test_empty_chunks_returns_zero(
        self, engine: ContextEngine, project_id: uuid.UUID
    ) -> None:
        result = await engine._embed_and_store(project_id, [], None)
        assert result == 0

    async def test_processes_chunks_correctly(
        self,
        engine: ContextEngine,
        project_id: uuid.UUID,
        mock_embedding_service: AsyncMock,
    ) -> None:
        chunks = [
            CodeChunk(
                file_path="a.py",
                start_line=1,
                end_line=5,
                chunk_type=ChunkType.FUNCTION,
                symbol_name="func_a",
                content="def func_a(): pass",
                language="python",
            ),
            CodeChunk(
                file_path="b.py",
                start_line=1,
                end_line=3,
                chunk_type=ChunkType.CLASS,
                symbol_name="MyClass",
                content="class MyClass: pass",
                language="python",
            ),
        ]

        mock_store = AsyncMock()
        mock_store.upsert_embeddings = AsyncMock(return_value=2)
        engine._store = mock_store
        mock_embedding_service.embed_texts.return_value = [[0.1] * 10, [0.2] * 10]

        result = await engine._embed_and_store(project_id, chunks, "sha123")
        assert result == 2
        mock_embedding_service.embed_texts.assert_awaited_once()
        mock_store.upsert_embeddings.assert_awaited_once()

        # Check the records passed to upsert
        call_args = mock_store.upsert_embeddings.call_args
        records = call_args[0][1]
        assert len(records) == 2
        assert records[0]["file_path"] == "a.py"
        assert records[0]["commit_sha"] == "sha123"
