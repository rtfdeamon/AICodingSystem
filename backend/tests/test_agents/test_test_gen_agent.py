"""Tests for app.agents.test_gen_agent — AI-powered test generation."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.agents.base import AgentResponse
from app.agents.test_gen_agent import (
    TestFile,
    _parse_test_output,
    generate_tests,
)

# ── _parse_test_output ───────────────────────────────────────────────


class TestParseTestOutput:
    def test_valid_json(self) -> None:
        raw = json.dumps(
            {
                "test_files": [
                    {
                        "file_path": "tests/test_auth.py",
                        "content": "def test_login(): pass",
                        "test_type": "unit",
                    }
                ]
            }
        )
        files = _parse_test_output(raw)
        assert len(files) == 1
        assert files[0].file_path == "tests/test_auth.py"
        assert files[0].content == "def test_login(): pass"
        assert files[0].test_type == "unit"

    def test_strips_markdown_fences(self) -> None:
        inner = json.dumps(
            {
                "test_files": [
                    {
                        "file_path": "tests/test_a.py",
                        "content": "test code",
                        "test_type": "integration",
                    }
                ]
            }
        )
        raw = f"```json\n{inner}\n```"
        files = _parse_test_output(raw)
        assert len(files) == 1
        assert files[0].test_type == "integration"

    def test_strips_plain_fences(self) -> None:
        inner = json.dumps(
            {
                "test_files": [
                    {
                        "file_path": "tests/test_b.py",
                        "content": "code",
                    }
                ]
            }
        )
        raw = f"```\n{inner}\n```"
        files = _parse_test_output(raw)
        assert len(files) == 1

    def test_invalid_json_raises(self) -> None:
        with pytest.raises(ValueError, match="invalid JSON"):
            _parse_test_output("definitely not json {{{")

    def test_missing_test_type_defaults_to_unit(self) -> None:
        raw = json.dumps(
            {
                "test_files": [
                    {
                        "file_path": "tests/test_c.py",
                        "content": "test code",
                    }
                ]
            }
        )
        files = _parse_test_output(raw)
        assert files[0].test_type == "unit"

    def test_empty_test_files(self) -> None:
        raw = json.dumps({"test_files": []})
        files = _parse_test_output(raw)
        assert files == []

    def test_no_test_files_key(self) -> None:
        raw = json.dumps({"other": "data"})
        files = _parse_test_output(raw)
        assert files == []

    def test_multiple_test_files(self) -> None:
        raw = json.dumps(
            {
                "test_files": [
                    {"file_path": "tests/test_a.py", "content": "a", "test_type": "unit"},
                    {"file_path": "tests/test_b.py", "content": "b", "test_type": "integration"},
                    {"file_path": "tests/test_c.py", "content": "c", "test_type": "e2e"},
                ]
            }
        )
        files = _parse_test_output(raw)
        assert len(files) == 3
        assert files[2].test_type == "e2e"


# ── TestFile dataclass ───────────────────────────────────────────────


class TestTestFile:
    def test_fields(self) -> None:
        tf = TestFile(
            file_path="tests/test_x.py",
            content="def test(): pass",
            test_type="unit",
        )
        assert tf.file_path == "tests/test_x.py"
        assert tf.content == "def test(): pass"
        assert tf.test_type == "unit"


# ── generate_tests (integration with mocks) ─────────────────────────


class TestGenerateTests:
    async def test_generates_test_files(self) -> None:
        ai_response = AgentResponse(
            content=json.dumps(
                {
                    "test_files": [
                        {
                            "file_path": "tests/test_feature.py",
                            "content": "import pytest\n\ndef test_feature():\n    assert True",
                            "test_type": "unit",
                        }
                    ]
                }
            ),
            model_id="gemini-2.5-flash",
            prompt_tokens=500,
            completion_tokens=300,
        )

        with (
            patch(
                "app.agents.test_gen_agent.route_task",
                return_value=AsyncMock(name="gemini"),
            ),
            patch(
                "app.agents.test_gen_agent.execute_with_fallback",
                return_value=ai_response,
            ),
        ):
            files = await generate_tests(
                diff="+ def new_feature():\n+     return True",
                ticket_description="Add a new feature",
                language="python",
            )

        assert len(files) == 1
        assert files[0].file_path == "tests/test_feature.py"
        assert "test_feature" in files[0].content

    async def test_truncates_large_diff(self) -> None:
        large_diff = "+" * 20000
        ai_response = AgentResponse(
            content=json.dumps({"test_files": []}),
            model_id="test",
        )

        with (
            patch(
                "app.agents.test_gen_agent.route_task",
                return_value=AsyncMock(name="gemini"),
            ),
            patch(
                "app.agents.test_gen_agent.execute_with_fallback",
                return_value=ai_response,
            ) as mock_exec,
        ):
            await generate_tests(
                diff=large_diff,
                ticket_description="Test",
            )

        # The prompt passed should have the diff truncated to 12000
        call_kwargs = mock_exec.call_args
        prompt_arg = call_kwargs[1].get("prompt") or call_kwargs[0][1]
        # The diff in the prompt template should be truncated
        assert len(prompt_arg) < len(large_diff)

    async def test_default_language_is_python(self) -> None:
        ai_response = AgentResponse(
            content=json.dumps({"test_files": []}),
            model_id="test",
        )

        with (
            patch(
                "app.agents.test_gen_agent.route_task",
                return_value=AsyncMock(name="gemini"),
            ),
            patch(
                "app.agents.test_gen_agent.execute_with_fallback",
                return_value=ai_response,
            ) as mock_exec,
        ):
            await generate_tests(
                diff="+ code",
                ticket_description="A feature",
            )

        # "python" should appear in the prompt
        call_kwargs = mock_exec.call_args
        prompt_arg = call_kwargs[1].get("prompt") or call_kwargs[0][1]
        assert "python" in prompt_arg

    async def test_passes_kwargs_to_execute(self) -> None:
        ai_response = AgentResponse(
            content=json.dumps({"test_files": []}),
            model_id="test",
        )

        mock_agent = AsyncMock(name="gemini")

        with (
            patch(
                "app.agents.test_gen_agent.route_task",
                return_value=mock_agent,
            ),
            patch(
                "app.agents.test_gen_agent.execute_with_fallback",
                return_value=ai_response,
            ) as mock_exec,
        ):
            import uuid

            tid = uuid.uuid4()
            await generate_tests(
                diff="+ code",
                ticket_description="Desc",
                db=AsyncMock(),
                ticket_id=tid,
            )

        # Verify kwargs were forwarded
        call_kwargs = mock_exec.call_args[1]
        assert "ticket_id" in call_kwargs
        assert call_kwargs["ticket_id"] == tid

    async def test_routes_to_test_generation_task(self) -> None:
        ai_response = AgentResponse(
            content=json.dumps({"test_files": []}),
            model_id="test",
        )

        with (
            patch(
                "app.agents.test_gen_agent.route_task",
                return_value=AsyncMock(name="gemini"),
            ) as mock_route,
            patch(
                "app.agents.test_gen_agent.execute_with_fallback",
                return_value=ai_response,
            ),
        ):
            await generate_tests(diff="+ x", ticket_description="test")

        mock_route.assert_called_once_with("test_generation")
