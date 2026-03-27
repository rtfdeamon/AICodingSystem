"""Tests for app.context.code_parser — semantic code chunking."""

from __future__ import annotations

import textwrap

from app.context.code_parser import (
    ChunkType,
    _detect_language,
    _find_block_end,
    _parse_js_ts,
    _parse_python,
    _sliding_window_chunks,
    parse_file,
)

# ── Language detection ────────────────────────────────────────────────


class TestDetectLanguage:
    def test_python(self) -> None:
        assert _detect_language("src/main.py") == "python"

    def test_javascript(self) -> None:
        assert _detect_language("index.js") == "javascript"
        assert _detect_language("App.jsx") == "javascript"

    def test_typescript(self) -> None:
        assert _detect_language("utils.ts") == "typescript"
        assert _detect_language("Component.tsx") == "typescript"

    def test_go(self) -> None:
        assert _detect_language("main.go") == "go"

    def test_rust(self) -> None:
        assert _detect_language("lib.rs") == "rust"

    def test_unknown_extension(self) -> None:
        assert _detect_language("file.xyz") == "unknown"

    def test_case_insensitive_via_path(self) -> None:
        assert _detect_language("Module.PY") == "python"

    def test_yaml(self) -> None:
        assert _detect_language("config.yaml") == "yaml"
        assert _detect_language("config.yml") == "yaml"

    def test_json(self) -> None:
        assert _detect_language("package.json") == "json"

    def test_markdown(self) -> None:
        assert _detect_language("README.md") == "markdown"

    def test_shell(self) -> None:
        assert _detect_language("deploy.sh") == "shell"
        assert _detect_language("build.bash") == "shell"

    def test_sql(self) -> None:
        assert _detect_language("schema.sql") == "sql"


# ── Python parser ────────────────────────────────────────────────────


class TestParsePython:
    def test_extracts_function(self) -> None:
        code = textwrap.dedent("""\
            def hello(name: str) -> str:
                return f"Hello, {name}"
        """)
        chunks = _parse_python("test.py", code)
        assert len(chunks) == 1
        assert chunks[0].chunk_type == ChunkType.FUNCTION
        assert chunks[0].symbol_name == "hello"
        assert chunks[0].start_line == 1
        assert chunks[0].end_line == 2
        assert chunks[0].language == "python"

    def test_extracts_async_function(self) -> None:
        code = textwrap.dedent("""\
            async def fetch_data(url: str) -> dict:
                pass
        """)
        chunks = _parse_python("test.py", code)
        assert len(chunks) == 1
        assert chunks[0].chunk_type == ChunkType.FUNCTION
        assert chunks[0].symbol_name == "fetch_data"

    def test_extracts_class(self) -> None:
        code = textwrap.dedent("""\
            class MyClass:
                def __init__(self):
                    self.x = 1

                def method(self):
                    return self.x
        """)
        chunks = _parse_python("test.py", code)
        # Should find the class and the methods inside it
        class_chunks = [c for c in chunks if c.chunk_type == ChunkType.CLASS]
        func_chunks = [c for c in chunks if c.chunk_type == ChunkType.FUNCTION]
        assert len(class_chunks) == 1
        assert class_chunks[0].symbol_name == "MyClass"
        assert len(func_chunks) == 2

    def test_syntax_error_returns_empty(self) -> None:
        code = "def broken(:\n    pass"
        chunks = _parse_python("test.py", code)
        assert chunks == []

    def test_no_functions_returns_empty(self) -> None:
        code = "x = 1\ny = 2\nprint(x + y)\n"
        chunks = _parse_python("test.py", code)
        assert chunks == []

    def test_multiple_functions(self) -> None:
        code = textwrap.dedent("""\
            def foo():
                pass

            def bar():
                pass

            def baz():
                pass
        """)
        chunks = _parse_python("test.py", code)
        names = [c.symbol_name for c in chunks]
        assert "foo" in names
        assert "bar" in names
        assert "baz" in names


# ── JS/TS parser ─────────────────────────────────────────────────────


class TestParseJsTs:
    def test_extracts_function(self) -> None:
        code = textwrap.dedent("""\
            function greet(name) {
                return `Hello, ${name}`;
            }
        """)
        chunks = _parse_js_ts("app.js", code, "javascript")
        assert len(chunks) == 1
        assert chunks[0].symbol_name == "greet"
        assert chunks[0].chunk_type == ChunkType.FUNCTION
        assert chunks[0].language == "javascript"

    def test_extracts_async_function(self) -> None:
        code = textwrap.dedent("""\
            async function fetchData(url) {
                return await fetch(url);
            }
        """)
        chunks = _parse_js_ts("app.js", code, "javascript")
        assert len(chunks) == 1
        assert chunks[0].symbol_name == "fetchData"

    def test_extracts_export_function(self) -> None:
        code = textwrap.dedent("""\
            export function helper() {
                return true;
            }
        """)
        chunks = _parse_js_ts("util.ts", code, "typescript")
        assert len(chunks) == 1
        assert chunks[0].symbol_name == "helper"

    def test_extracts_arrow_function(self) -> None:
        code = textwrap.dedent("""\
            const add = (a, b) => {
                return a + b;
            }
        """)
        chunks = _parse_js_ts("util.js", code, "javascript")
        assert len(chunks) == 1
        assert chunks[0].symbol_name == "add"

    def test_extracts_class(self) -> None:
        code = textwrap.dedent("""\
            class UserService {
                constructor() {
                    this.users = [];
                }
            }
        """)
        chunks = _parse_js_ts("service.ts", code, "typescript")
        assert len(chunks) == 1
        assert chunks[0].symbol_name == "UserService"
        assert chunks[0].chunk_type == ChunkType.CLASS

    def test_export_default_class(self) -> None:
        code = textwrap.dedent("""\
            export default class App {
                render() {
                    return null;
                }
            }
        """)
        chunks = _parse_js_ts("App.tsx", code, "typescript")
        assert len(chunks) == 1
        assert chunks[0].symbol_name == "App"

    def test_no_duplicates_for_same_range(self) -> None:
        code = textwrap.dedent("""\
            function only() {
                return 1;
            }
        """)
        chunks = _parse_js_ts("app.js", code, "javascript")
        ranges = [(c.start_line, c.end_line) for c in chunks]
        assert len(ranges) == len(set(ranges))


# ── find_block_end ───────────────────────────────────────────────────


class TestFindBlockEnd:
    def test_simple_block(self) -> None:
        lines = ["function f() {\n", "  return 1;\n", "}\n"]
        assert _find_block_end(lines, 0) == 2

    def test_nested_blocks(self) -> None:
        lines = [
            "function f() {\n",
            "  if (true) {\n",
            "    return 1;\n",
            "  }\n",
            "}\n",
        ]
        assert _find_block_end(lines, 0) == 4

    def test_no_closing_brace_returns_capped(self) -> None:
        lines = ["function f() {\n", "  return 1;\n"]
        result = _find_block_end(lines, 0)
        # Should return min(start + 80, len - 1)
        assert result <= 80


# ── Sliding window ───────────────────────────────────────────────────


class TestSlidingWindowChunks:
    def test_short_file_single_chunk(self) -> None:
        content = "line\n" * 10
        chunks = _sliding_window_chunks("file.go", content, "go")
        assert len(chunks) == 1
        assert chunks[0].chunk_type == ChunkType.MODULE
        assert chunks[0].language == "go"

    def test_empty_content(self) -> None:
        chunks = _sliding_window_chunks("file.go", "", "go")
        assert chunks == []

    def test_large_file_multiple_chunks(self) -> None:
        content = "line\n" * 200
        chunks = _sliding_window_chunks("file.rs", content, "rust")
        assert len(chunks) > 1
        # Check overlap: second chunk should start before first chunk ends
        assert chunks[1].start_line < chunks[0].end_line + 1

    def test_symbol_names_are_sequential(self) -> None:
        content = "line\n" * 200
        chunks = _sliding_window_chunks("file.go", content, "go")
        for i, chunk in enumerate(chunks):
            assert chunk.symbol_name == f"chunk_{i}"


# ── parse_file (public API) ──────────────────────────────────────────


class TestParseFile:
    def test_empty_content(self) -> None:
        assert parse_file("test.py", "") == []

    def test_whitespace_only(self) -> None:
        assert parse_file("test.py", "   \n\n  ") == []

    def test_python_file_uses_ast(self) -> None:
        code = textwrap.dedent("""\
            def my_func():
                return 42
        """)
        chunks = parse_file("module.py", code)
        assert len(chunks) >= 1
        assert any(c.symbol_name == "my_func" for c in chunks)

    def test_js_file_uses_regex(self) -> None:
        code = textwrap.dedent("""\
            function doThing() {
                return true;
            }
        """)
        chunks = parse_file("app.js", code)
        assert len(chunks) >= 1
        assert any(c.symbol_name == "doThing" for c in chunks)

    def test_ts_file_uses_regex(self) -> None:
        code = textwrap.dedent("""\
            export function helper() {
                return 1;
            }
        """)
        chunks = parse_file("util.ts", code)
        assert len(chunks) >= 1

    def test_unknown_language_uses_sliding_window(self) -> None:
        code = "some content\n" * 5
        chunks = parse_file("config.toml", code)
        assert len(chunks) >= 1
        assert chunks[0].chunk_type == ChunkType.MODULE

    def test_python_file_no_symbols_falls_back(self) -> None:
        code = "x = 1\ny = 2\nprint(x + y)\n"
        chunks = parse_file("script.py", code)
        # Falls back to sliding window since no functions/classes found
        assert len(chunks) >= 1
        assert chunks[0].chunk_type == ChunkType.MODULE

    def test_file_path_preserved(self) -> None:
        code = "def f():\n    pass\n"
        chunks = parse_file("src/utils/helpers.py", code)
        for chunk in chunks:
            assert chunk.file_path == "src/utils/helpers.py"
