"""Context Engine — orchestrates code parsing, embedding, and retrieval."""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.context.code_parser import CodeChunk, parse_file
from app.context.embeddings import EmbeddingService
from app.context.vector_store import SearchResult, VectorStore

logger = logging.getLogger(__name__)

# File extensions we consider indexable source code
_INDEXABLE_EXTENSIONS: set[str] = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".go",
    ".rs",
    ".java",
    ".rb",
    ".c",
    ".cpp",
    ".h",
    ".hpp",
    ".cs",
    ".swift",
    ".kt",
    ".php",
    ".sh",
    ".bash",
    ".sql",
    ".yaml",
    ".yml",
    ".toml",
    ".json",
    ".md",
}

# Maximum file size to index (256 KB) — skip large vendored / generated files
_MAX_FILE_SIZE = 256 * 1024

# Directories to skip during traversal
_SKIP_DIRS: set[str] = {
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "dist",
    "build",
    ".next",
    ".nuxt",
    "target",
    "vendor",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    "coverage",
}


class ContextEngine:
    """High-level orchestrator for code context indexing and retrieval.

    Parameters
    ----------
    session:
        An async SQLAlchemy session for persistence.
    embedding_service:
        Optional custom :class:`EmbeddingService` instance.  If *None*,
        one is created using the default API key from settings.
    """

    def __init__(
        self,
        session: AsyncSession,
        embedding_service: EmbeddingService | None = None,
    ) -> None:
        self._session = session
        self._embeddings = embedding_service or EmbeddingService()
        self._store = VectorStore(session)

    # ── full index ────────────────────────────────────────────────────

    async def index_repo(
        self,
        project_id: uuid.UUID,
        repo_path: str | Path,
        commit_sha: str | None = None,
    ) -> dict[str, Any]:
        """Index (or re-index) the entire repository at *repo_path*.

        1. Walks the file tree, skipping non-indexable files.
        2. Parses each file into semantic chunks.
        3. Generates embeddings in batches.
        4. Upserts into the vector store (old data is replaced).

        Returns a summary dict with counts.
        """
        repo = Path(repo_path)
        if not repo.is_dir():
            raise FileNotFoundError(f"Repository path does not exist: {repo}")

        logger.info(
            "Starting full index of project %s from %s (commit=%s)",
            project_id,
            repo,
            commit_sha,
        )

        # Delete existing embeddings to do a clean re-index
        await self._store.delete_project_embeddings(project_id)

        all_chunks = self._collect_chunks(repo)
        upserted = await self._embed_and_store(project_id, all_chunks, commit_sha)

        summary = {
            "files_scanned": len({c.file_path for c in all_chunks}),
            "chunks_indexed": upserted,
            "commit_sha": commit_sha,
        }
        logger.info("Full index complete for project %s: %s", project_id, summary)
        return summary

    # ── incremental index ─────────────────────────────────────────────

    async def incremental_index(
        self,
        project_id: uuid.UUID,
        repo_path: str | Path,
        changed_files: list[str],
        commit_sha: str | None = None,
    ) -> dict[str, Any]:
        """Re-index only the *changed_files* within a repository.

        Deletes old embeddings for each changed file, then parses and
        re-embeds just those files.
        """
        repo = Path(repo_path)
        logger.info(
            "Incremental index for project %s: %d changed file(s)",
            project_id,
            len(changed_files),
        )

        chunks: list[CodeChunk] = []
        for rel_path in changed_files:
            full_path = repo / rel_path
            if not full_path.is_file():
                # File may have been deleted — remove its embeddings
                await self._store.delete_file_embeddings(project_id, rel_path)
                continue

            if full_path.suffix.lower() not in _INDEXABLE_EXTENSIONS:
                continue
            if full_path.stat().st_size > _MAX_FILE_SIZE:
                continue

            try:
                content = full_path.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                logger.warning("Cannot read %s: %s", full_path, exc)
                continue

            file_chunks = parse_file(rel_path, content)
            chunks.extend(file_chunks)

        upserted = await self._embed_and_store(project_id, chunks, commit_sha)

        summary = {
            "files_updated": len(changed_files),
            "chunks_indexed": upserted,
            "commit_sha": commit_sha,
        }
        logger.info("Incremental index complete for project %s: %s", project_id, summary)
        return summary

    # ── search ────────────────────────────────────────────────────────

    async def search(
        self,
        project_id: uuid.UUID,
        query: str,
        top_k: int = 10,
    ) -> list[SearchResult]:
        """Perform semantic search across the indexed code for a project."""
        query_embedding = await self._embeddings.embed_single(query)
        results = await self._store.search(project_id, query_embedding, top_k=top_k)
        logger.info(
            "Search for project %s returned %d results (query=%s...)",
            project_id,
            len(results),
            query[:60],
        )
        return results

    # ── context for ticket ────────────────────────────────────────────

    async def get_context_for_ticket(
        self,
        project_id: uuid.UUID,
        ticket_description: str,
        acceptance_criteria: str | None = None,
    ) -> str:
        """Build a formatted context string for an AI coding agent.

        Combines the ticket description and acceptance criteria into a
        search query, retrieves the most relevant code chunks, and
        formats them into a string suitable for an LLM prompt.
        """
        query_parts = [ticket_description]
        if acceptance_criteria:
            query_parts.append(acceptance_criteria)
        query = "\n".join(query_parts)

        results = await self.search(project_id, query, top_k=10)

        if not results:
            return "No relevant code context found in the repository."

        sections: list[str] = []
        for i, r in enumerate(results, 1):
            header = f"--- [{i}] {r.file_path}"
            if r.symbol_name:
                header += f" :: {r.symbol_name}"
            header += f" (score: {r.score:.3f}) ---"
            sections.append(header)
            sections.append(r.chunk_text)
            sections.append("")

        return "\n".join(sections)

    # ── private helpers ───────────────────────────────────────────────

    def _collect_chunks(self, repo: Path) -> list[CodeChunk]:
        """Walk the repo tree and parse all indexable files into chunks."""
        all_chunks: list[CodeChunk] = []

        for path in repo.rglob("*"):
            # Skip directories in the exclusion list
            if any(part in _SKIP_DIRS for part in path.parts):
                continue
            if not path.is_file():
                continue
            if path.suffix.lower() not in _INDEXABLE_EXTENSIONS:
                continue
            if path.stat().st_size > _MAX_FILE_SIZE:
                continue

            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                logger.warning("Cannot read %s: %s", path, exc)
                continue

            rel_path = str(path.relative_to(repo))
            file_chunks = parse_file(rel_path, content)
            all_chunks.extend(file_chunks)

        logger.info(
            "Collected %d chunks from %d files in %s",
            len(all_chunks),
            len({c.file_path for c in all_chunks}),
            repo,
        )
        return all_chunks

    async def _embed_and_store(
        self,
        project_id: uuid.UUID,
        chunks: list[CodeChunk],
        commit_sha: str | None,
    ) -> int:
        """Embed chunks and upsert into the vector store.  Returns upsert count."""
        if not chunks:
            return 0

        texts = [c.content for c in chunks]
        embeddings = await self._embeddings.embed_texts(texts)

        records: list[dict[str, Any]] = []
        for i, chunk in enumerate(chunks):
            records.append(
                {
                    "file_path": chunk.file_path,
                    "chunk_index": i,
                    "chunk_text": chunk.content,
                    "language": chunk.language,
                    "symbol_name": chunk.symbol_name,
                    "embedding": embeddings[i],
                    "commit_sha": commit_sha,
                }
            )

        return await self._store.upsert_embeddings(project_id, records)
