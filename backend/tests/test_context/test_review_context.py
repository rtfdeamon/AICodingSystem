"""Tests for review context engine — symbol extraction, usage search, prompt building."""

from __future__ import annotations

import uuid

from app.context.review_context import (
    HistoricalPR,
    ReviewContext,
    SymbolUsage,
    build_review_context_prompt,
    extract_symbols_from_diff,
    find_symbol_usages,
    review_context_to_json,
)

# ── Symbol extraction from diffs ──────────────────────────────────────


class TestExtractSymbolsFromDiff:
    def test_extracts_python_function_def(self) -> None:
        diff = "+def calculate_total(items):\n+    return sum(items)"
        symbols = extract_symbols_from_diff(diff)
        assert "calculate_total" in symbols

    def test_extracts_python_class_def(self) -> None:
        diff = "+class UserService:\n+    pass"
        symbols = extract_symbols_from_diff(diff)
        assert "UserService" in symbols

    def test_extracts_python_async_def(self) -> None:
        diff = "+async def fetch_data(url):\n+    return await get(url)"
        symbols = extract_symbols_from_diff(diff)
        assert "fetch_data" in symbols

    def test_extracts_python_imports(self) -> None:
        diff = "+from app.services import AuthService, UserService"
        symbols = extract_symbols_from_diff(diff)
        assert "AuthService" in symbols
        assert "UserService" in symbols

    def test_extracts_typescript_imports(self) -> None:
        diff = "+import { useState, useEffect } from 'react'"
        symbols = extract_symbols_from_diff(diff)
        assert "useState" in symbols
        assert "useEffect" in symbols

    def test_extracts_ts_function_export(self) -> None:
        diff = "+export function handleSubmit(data) {"
        symbols = extract_symbols_from_diff(diff)
        assert "handleSubmit" in symbols

    def test_ignores_removed_lines(self) -> None:
        diff = "-def old_function():\n+def new_function():"
        symbols = extract_symbols_from_diff(diff)
        assert "new_function" in symbols
        assert "old_function" not in symbols

    def test_filters_noise_keywords(self) -> None:
        diff = "+if True:\n+    return None"
        symbols = extract_symbols_from_diff(diff)
        assert "if" not in symbols
        assert "True" not in symbols
        assert "return" not in symbols
        assert "None" not in symbols

    def test_ignores_diff_header(self) -> None:
        diff = "+++ b/app/main.py\n+def main():"
        symbols = extract_symbols_from_diff(diff)
        assert "main" in symbols

    def test_returns_sorted_deduplicated(self) -> None:
        diff = "+def foo():\n+def bar():\n+foo()\n+bar()"
        symbols = extract_symbols_from_diff(diff)
        assert symbols == sorted(set(symbols))

    def test_empty_diff_returns_empty(self) -> None:
        assert extract_symbols_from_diff("") == []


# ── Symbol usage search ───────────────────────────────────────────────


class TestFindSymbolUsages:
    def test_finds_import_usage(self) -> None:
        files = {"app/main.py": "from app.utils import calculate_total\n"}
        usages = find_symbol_usages("calculate_total", files)
        assert len(usages) == 1
        assert usages[0].usage_type == "import"
        assert usages[0].file_path == "app/main.py"

    def test_finds_call_usage(self) -> None:
        files = {"app/service.py": "result = calculate_total(items)\n"}
        usages = find_symbol_usages("calculate_total", files)
        assert len(usages) == 1
        assert usages[0].usage_type == "call"

    def test_finds_definition(self) -> None:
        files = {"app/utils.py": "def calculate_total(items):\n    return sum(items)"}
        usages = find_symbol_usages("calculate_total", files)
        assert any(u.usage_type == "definition" for u in usages)

    def test_finds_reference(self) -> None:
        files = {"docs/api.md": "The calculate_total function is used for billing"}
        usages = find_symbol_usages("calculate_total", files)
        assert len(usages) == 1
        assert usages[0].usage_type == "reference"

    def test_respects_max_results(self) -> None:
        files = {f"file{i}.py": "calculate_total(x)\n" for i in range(20)}
        usages = find_symbol_usages("calculate_total", files, max_results=5)
        assert len(usages) <= 5

    def test_no_matches_returns_empty(self) -> None:
        files = {"app/main.py": "import os\nprint('hello')"}
        usages = find_symbol_usages("nonexistent", files)
        assert usages == []

    def test_records_line_numbers(self) -> None:
        files = {"app/main.py": "line1\nline2\ncalculate_total(x)\nline4"}
        usages = find_symbol_usages("calculate_total", files)
        assert usages[0].line_number == 3


# ── Review context prompt building ───────────────────────────────────


class TestBuildReviewContextPrompt:
    def test_includes_coding_standards(self) -> None:
        ctx = ReviewContext(coding_standards="Use type hints everywhere")
        prompt = build_review_context_prompt(ctx)
        assert "Coding Standards" in prompt
        assert "type hints" in prompt

    def test_includes_architecture_notes(self) -> None:
        ctx = ReviewContext(architecture_notes="Hexagonal architecture")
        prompt = build_review_context_prompt(ctx)
        assert "Architecture Notes" in prompt
        assert "Hexagonal" in prompt

    def test_includes_symbol_usages(self) -> None:
        ctx = ReviewContext(
            symbol_usages={
                "MyFunc": [
                    SymbolUsage(
                        file_path="app/main.py",
                        line_number=10,
                        usage_type="call",
                        snippet="MyFunc(args)",
                    )
                ]
            }
        )
        prompt = build_review_context_prompt(ctx)
        assert "MyFunc" in prompt
        assert "app/main.py" in prompt

    def test_includes_historical_prs(self) -> None:
        ctx = ReviewContext(
            historical_prs=[
                HistoricalPR(
                    ticket_id=uuid.uuid4(),
                    title="Fix auth bug",
                    decision="approved",
                    findings_count=3,
                )
            ]
        )
        prompt = build_review_context_prompt(ctx)
        assert "Historical Reviews" in prompt
        assert "Fix auth bug" in prompt

    def test_includes_related_files(self) -> None:
        ctx = ReviewContext(related_files=["app/utils.py", "app/models.py"])
        prompt = build_review_context_prompt(ctx)
        assert "Related Files" in prompt
        assert "app/utils.py" in prompt

    def test_sets_context_tokens(self) -> None:
        ctx = ReviewContext(coding_standards="x" * 1000)
        build_review_context_prompt(ctx)
        assert ctx.context_tokens > 0

    def test_empty_context_produces_minimal_prompt(self) -> None:
        ctx = ReviewContext()
        prompt = build_review_context_prompt(ctx)
        assert len(prompt) < 50  # Just whitespace


# ── JSON serialization ───────────────────────────────────────────────


class TestReviewContextToJson:
    def test_serializes_complete_context(self) -> None:
        tid = uuid.uuid4()
        ctx = ReviewContext(
            symbol_usages={
                "foo": [SymbolUsage("a.py", 1, "call", "foo()")]
            },
            historical_prs=[
                HistoricalPR(ticket_id=tid, title="test", decision="approved")
            ],
            related_files=["b.py"],
            context_tokens=100,
        )
        data = review_context_to_json(ctx)
        assert "foo" in data["symbol_usages"]
        assert len(data["historical_prs"]) == 1
        assert data["related_files"] == ["b.py"]
        assert data["context_tokens"] == 100
