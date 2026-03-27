"""Review Context Engine — enriches code reviews with cross-repo usages and historical PRs.

Collects contextual signals to improve AI review quality:
- Cross-repo symbol usages (callers, importers, dependents)
- Historical PR patterns (past changes to same files, recurring issues)
- Architecture docs and coding standards as grounding context
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.review import Review, ReviewerType
from app.models.ticket import Ticket

logger = logging.getLogger(__name__)


@dataclass
class SymbolUsage:
    """A location where a symbol is referenced across the codebase."""

    file_path: str
    line_number: int
    usage_type: str  # "import", "call", "reference", "definition"
    snippet: str = ""


@dataclass
class HistoricalPR:
    """A past review/PR that touched the same files."""

    ticket_id: uuid.UUID
    title: str
    files_changed: list[str] = field(default_factory=list)
    decision: str = ""
    findings_count: int = 0
    date: datetime | None = None


@dataclass
class ReviewContext:
    """Enriched context for a code review."""

    symbol_usages: dict[str, list[SymbolUsage]] = field(default_factory=dict)
    historical_prs: list[HistoricalPR] = field(default_factory=list)
    architecture_notes: str = ""
    coding_standards: str = ""
    related_files: list[str] = field(default_factory=list)
    context_tokens: int = 0


# ── Symbol extraction ──────────────────────────────────────────────────

_PYTHON_IMPORT_RE = re.compile(
    r"^(?:from\s+([\w.]+)\s+)?import\s+([\w,\s]+)", re.MULTILINE
)
_PYTHON_DEF_RE = re.compile(r"^(?:def|class|async\s+def)\s+(\w+)", re.MULTILINE)
_PYTHON_CALL_RE = re.compile(r"\b(\w{2,})\s*\(", re.MULTILINE)

_TS_IMPORT_RE = re.compile(
    r"import\s+(?:\{([^}]+)\}|(\w+))\s+from\s+['\"]([^'\"]+)['\"]", re.MULTILINE
)
_TS_FUNC_RE = re.compile(
    r"(?:export\s+)?(?:function|const|class)\s+(\w+)", re.MULTILINE
)


def extract_symbols_from_diff(diff: str) -> list[str]:
    """Extract symbol names (functions, classes, imports) from a diff.

    Returns a deduplicated list of symbol names found in added/changed lines.
    """
    symbols: set[str] = set()
    for line in diff.splitlines():
        if not line.startswith("+") or line.startswith("+++"):
            continue
        content = line[1:].strip()
        if not content:
            continue

        # Python definitions
        for m in _PYTHON_DEF_RE.finditer(content):
            symbols.add(m.group(1))

        # Python imports
        for m in _PYTHON_IMPORT_RE.finditer(content):
            if m.group(2):
                for raw_name in m.group(2).split(","):
                    clean = raw_name.strip()
                    if clean and len(clean) > 1:
                        symbols.add(clean)

        # TypeScript imports
        for m in _TS_IMPORT_RE.finditer(content):
            if m.group(1):
                for raw_name in m.group(1).split(","):
                    clean = raw_name.strip()
                    if clean and len(clean) > 1:
                        symbols.add(clean)
            if m.group(2):
                symbols.add(m.group(2))

        # TypeScript/JS function/class definitions
        for m in _TS_FUNC_RE.finditer(content):
            symbols.add(m.group(1))

    # Filter out common noise
    noise = {
        "if", "else", "for", "while", "return", "True", "False", "None",
        "true", "false", "null", "undefined", "self", "cls", "this",
        "print", "len", "str", "int", "dict", "list", "set", "type",
        "async", "await", "const", "let", "var",
    }
    return sorted(symbols - noise)


def find_symbol_usages(
    symbol: str,
    file_contents: dict[str, str],
    *,
    max_results: int = 10,
) -> list[SymbolUsage]:
    """Find usages of a symbol across multiple files.

    Parameters
    ----------
    symbol:
        The symbol name to search for.
    file_contents:
        Dict of {file_path: file_content} to search.
    max_results:
        Maximum number of usages to return per symbol.
    """
    usages: list[SymbolUsage] = []
    pattern = re.compile(rf"\b{re.escape(symbol)}\b")

    for file_path, content in file_contents.items():
        for line_num, line in enumerate(content.splitlines(), 1):
            if pattern.search(line):
                stripped = line.strip()
                # Determine usage type
                if re.match(r"^(?:from|import)\s", stripped):
                    usage_type = "import"
                elif re.match(rf"^(?:def|class|async\s+def)\s+{re.escape(symbol)}\b", stripped):
                    usage_type = "definition"
                elif f"{symbol}(" in stripped:
                    usage_type = "call"
                else:
                    usage_type = "reference"

                usages.append(SymbolUsage(
                    file_path=file_path,
                    line_number=line_num,
                    usage_type=usage_type,
                    snippet=stripped[:200],
                ))

                if len(usages) >= max_results:
                    return usages

    return usages


async def get_historical_reviews(
    db: AsyncSession,
    project_id: uuid.UUID,
    changed_files: list[str],
    *,
    lookback_days: int = 90,
    limit: int = 10,
) -> list[HistoricalPR]:
    """Find past reviews that touched the same files.

    Returns recent reviews for the same project whose diff_snippet
    references any of the given changed_files.
    """
    cutoff = datetime.now(UTC) - timedelta(days=lookback_days)
    ticket_ids_subq = select(Ticket.id).where(Ticket.project_id == project_id).subquery()

    # Get recent reviews
    result = await db.execute(
        select(
            Review.id,
            Review.ticket_id,
            Review.decision,
            Review.summary,
            Review.created_at,
            Review.inline_comments,
        )
        .where(
            Review.ticket_id.in_(select(ticket_ids_subq)),
            Review.reviewer_type == ReviewerType.AI_AGENT,
            Review.created_at >= cutoff,
        )
        .order_by(Review.created_at.desc())
        .limit(limit * 3)  # Fetch more, filter below
    )

    historical: list[HistoricalPR] = []
    for row in result.all():
        # Check if this review touched any of our changed files
        review_files: list[str] = []
        inline = row.inline_comments or []
        if isinstance(inline, list):
            for comment in inline:
                if isinstance(comment, dict) and "file" in comment:
                    review_files.append(comment["file"])

        # Match by file overlap
        overlap = set(review_files) & set(changed_files)
        if overlap or not changed_files:
            decision = row.decision
            if hasattr(decision, "value"):
                decision = decision.value
            historical.append(HistoricalPR(
                ticket_id=row.ticket_id,
                title=row.summary or "",
                files_changed=review_files,
                decision=str(decision) if decision else "",
                findings_count=len(inline) if isinstance(inline, list) else 0,
                date=row.created_at,
            ))

        if len(historical) >= limit:
            break

    return historical


def build_review_context_prompt(context: ReviewContext) -> str:
    """Build a context prompt section from enriched review context.

    This is appended to the review agent's prompt to ground its analysis.
    """
    parts: list[str] = []

    if context.coding_standards:
        parts.append(f"## Coding Standards\n{context.coding_standards[:2000]}\n")

    if context.architecture_notes:
        parts.append(f"## Architecture Notes\n{context.architecture_notes[:2000]}\n")

    if context.symbol_usages:
        parts.append("## Symbol Usages Across Codebase\n")
        for symbol, usages in list(context.symbol_usages.items())[:5]:
            parts.append(f"### `{symbol}` ({len(usages)} usage(s))\n")
            for u in usages[:3]:
                parts.append(
                    f"- {u.file_path}:{u.line_number} [{u.usage_type}]: `{u.snippet[:100]}`\n"
                )

    if context.historical_prs:
        parts.append("## Historical Reviews for Same Files\n")
        for pr in context.historical_prs[:5]:
            date_str = pr.date.strftime("%Y-%m-%d") if pr.date else "unknown"
            parts.append(
                f"- [{date_str}] {pr.title[:100]} — "
                f"decision: {pr.decision}, findings: {pr.findings_count}\n"
            )

    if context.related_files:
        parts.append("## Related Files\n")
        for f in context.related_files[:10]:
            parts.append(f"- {f}\n")

    text = "\n".join(parts)
    context.context_tokens = len(text) // 4  # Rough token estimate
    return text


def review_context_to_json(context: ReviewContext) -> dict[str, Any]:
    """Serialize ReviewContext to JSON-compatible dict."""
    return {
        "symbol_usages": {
            sym: [
                {
                    "file_path": u.file_path,
                    "line_number": u.line_number,
                    "usage_type": u.usage_type,
                    "snippet": u.snippet,
                }
                for u in usages
            ]
            for sym, usages in context.symbol_usages.items()
        },
        "historical_prs": [
            {
                "ticket_id": str(pr.ticket_id),
                "title": pr.title,
                "files_changed": pr.files_changed,
                "decision": pr.decision,
                "findings_count": pr.findings_count,
            }
            for pr in context.historical_prs
        ],
        "related_files": context.related_files,
        "context_tokens": context.context_tokens,
    }
