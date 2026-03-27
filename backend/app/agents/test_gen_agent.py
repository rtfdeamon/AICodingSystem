"""Test Generation Agent — AI-powered test creation from diffs."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from app.agents.router import execute_with_fallback, route_task

logger = logging.getLogger(__name__)

# ── Prompt templates ─────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are an expert QA engineer.  Generate comprehensive tests for the provided
code changes.

Your output MUST be valid JSON with exactly one key:
  - "test_files": an array of test-file objects.

Each test-file object MUST have:
  - "file_path": the path where the test file should be saved (follow project conventions).
  - "content": the complete test file content.
  - "test_type": one of "unit", "integration", "e2e".

Rules:
  - Generate at least 3 edge-case tests per endpoint or function.
  - Cover happy paths, error cases, boundary conditions, and security edge cases.
  - Use the appropriate test framework (pytest for Python, jest/vitest for JS/TS).
  - Include proper mocks, fixtures, and test isolation.
  - Follow AAA (Arrange-Act-Assert) pattern.
  - Respond ONLY with the JSON object.\
"""

_USER_PROMPT_TEMPLATE = """\
## Ticket Description
{ticket_description}

## Language
{language}

## Code Diff
```
{diff}
```

---

Generate comprehensive test files for the above changes.\
"""


@dataclass
class TestFile:
    __test__ = False  # prevent pytest from collecting this dataclass
    """A generated test file."""

    file_path: str
    content: str
    test_type: str  # "unit" | "integration" | "e2e"


def _parse_test_output(raw: str) -> list[TestFile]:
    """Parse JSON output into TestFile objects."""
    content = raw.strip()
    if content.startswith("```"):
        lines = content.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        content = "\n".join(lines)

    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Test gen agent returned invalid JSON: {exc}") from exc

    test_files: list[TestFile] = []
    for tf in data.get("test_files", []):
        test_files.append(
            TestFile(
                file_path=tf["file_path"],
                content=tf["content"],
                test_type=tf.get("test_type", "unit"),
            )
        )
    return test_files


async def generate_tests(
    diff: str,
    ticket_description: str,
    language: str = "python",
    **kwargs: Any,
) -> list[TestFile]:
    """Generate test files for the given code diff.

    Uses Gemini by default (routed via ``test_generation`` task type) for
    cost-effective test generation, with fallback to other agents.

    Parameters
    ----------
    diff:
        The unified diff of code changes.
    ticket_description:
        Human-readable description of what the changes implement.
    language:
        Primary language of the codebase (affects framework selection).
    **kwargs:
        Forwarded to ``execute_with_fallback`` (e.g. ``db``, ``ticket_id``).
    """
    user_prompt = _USER_PROMPT_TEMPLATE.format(
        ticket_description=ticket_description,
        language=language,
        diff=diff[:12_000],  # Truncate very large diffs
    )

    agent = route_task("test_generation")
    response = await execute_with_fallback(
        agent,
        prompt=user_prompt,
        context="",
        system_prompt=_SYSTEM_PROMPT,
        temperature=0.3,
        max_tokens=8192,
        action_type="test_generation",
        **kwargs,
    )

    test_files = _parse_test_output(response.content)

    logger.info(
        "Generated %d test file(s) for %s diff (%d chars): %s",
        len(test_files),
        language,
        len(diff),
        [tf.file_path for tf in test_files],
    )
    return test_files
