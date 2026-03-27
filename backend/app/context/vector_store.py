"""pgvector adapter for code embedding storage and similarity search."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.code_embedding import CodeEmbedding

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """A single similarity-search result."""

    file_path: str
    chunk_index: int
    chunk_text: str
    language: str
    symbol_name: str | None
    score: float
    commit_sha: str | None


class VectorStore:
    """Manages code embeddings in PostgreSQL using pgvector.

    Parameters
    ----------
    session:
        An :class:`AsyncSession` — typically injected via FastAPI dependency.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert_embeddings(
        self,
        project_id: uuid.UUID,
        chunks: list[dict[str, Any]],
    ) -> int:
        """Insert or update embedding rows for a set of code chunks.

        Each element in *chunks* must contain:
        - ``file_path`` (str)
        - ``chunk_index`` (int)
        - ``chunk_text`` (str)
        - ``language`` (str)
        - ``symbol_name`` (str | None)
        - ``embedding`` (list[float])
        - ``commit_sha`` (str | None)

        Existing rows for the same ``(project_id, file_path, chunk_index)``
        are deleted before insertion so the data is always current.

        Returns the number of rows upserted.
        """
        if not chunks:
            return 0

        # Group by file_path for efficient deletion
        file_paths = {c["file_path"] for c in chunks}
        for fp in file_paths:
            await self._session.execute(
                delete(CodeEmbedding).where(
                    CodeEmbedding.project_id == project_id,
                    CodeEmbedding.file_path == fp,
                )
            )

        rows: list[CodeEmbedding] = []
        for chunk in chunks:
            row = CodeEmbedding(
                project_id=project_id,
                file_path=chunk["file_path"],
                chunk_index=chunk["chunk_index"],
                chunk_text=chunk["chunk_text"],
                language=chunk["language"],
                symbol_name=chunk.get("symbol_name"),
                embedding=chunk["embedding"],
                commit_sha=chunk.get("commit_sha"),
            )
            rows.append(row)

        self._session.add_all(rows)
        await self._session.flush()
        logger.info(
            "Upserted %d embeddings for project %s (%d files)",
            len(rows),
            project_id,
            len(file_paths),
        )
        return len(rows)

    async def search(
        self,
        project_id: uuid.UUID,
        query_embedding: list[float],
        top_k: int = 10,
    ) -> list[SearchResult]:
        """Perform cosine-similarity search within a project.

        Uses pgvector's ``<=>`` (cosine distance) operator for ranking.
        Returns up to *top_k* results ordered by relevance.
        """
        # Use raw SQL for the pgvector distance operator
        stmt = text(
            """
            SELECT
                file_path,
                chunk_index,
                chunk_text,
                language,
                symbol_name,
                commit_sha,
                1 - (embedding <=> :query_vec) AS score
            FROM code_embeddings
            WHERE project_id = :project_id
            ORDER BY embedding <=> :query_vec
            LIMIT :top_k
            """
        )

        result = await self._session.execute(
            stmt,
            {
                "project_id": str(project_id),
                "query_vec": str(query_embedding),
                "top_k": top_k,
            },
        )
        rows = result.fetchall()

        return [
            SearchResult(
                file_path=row.file_path,
                chunk_index=row.chunk_index,
                chunk_text=row.chunk_text,
                language=row.language,
                symbol_name=row.symbol_name,
                score=float(row.score),
                commit_sha=row.commit_sha,
            )
            for row in rows
        ]

    async def delete_project_embeddings(self, project_id: uuid.UUID) -> int:
        """Delete all embeddings for a project.  Returns the count deleted."""
        result = await self._session.execute(
            delete(CodeEmbedding).where(CodeEmbedding.project_id == project_id)
        )
        count: int = result.rowcount  # type: ignore[attr-defined]
        logger.info("Deleted %d embeddings for project %s", count, project_id)
        return count

    async def delete_file_embeddings(
        self,
        project_id: uuid.UUID,
        file_path: str,
    ) -> int:
        """Delete all embeddings for a specific file within a project."""
        result = await self._session.execute(
            delete(CodeEmbedding).where(
                CodeEmbedding.project_id == project_id,
                CodeEmbedding.file_path == file_path,
            )
        )
        count: int = result.rowcount  # type: ignore[attr-defined]
        logger.info(
            "Deleted %d embeddings for %s in project %s",
            count,
            file_path,
            project_id,
        )
        return count
