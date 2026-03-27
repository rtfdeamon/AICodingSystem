"""Hallucination Detection Pipeline for Generated Code.

Scans AI-generated code for common hallucination patterns: fabricated imports,
nonexistent API calls, syntax errors, inconsistent variable usage, and other
indicators that the model invented code constructs that do not exist.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import StrEnum

logger = logging.getLogger(__name__)


class HallucinationType(StrEnum):
    FABRICATED_IMPORT = "fabricated_import"
    NONEXISTENT_API = "nonexistent_api"
    INVALID_SYNTAX = "invalid_syntax"
    INCONSISTENT_LOGIC = "inconsistent_logic"
    PHANTOM_VARIABLE = "phantom_variable"
    IMPOSSIBLE_TYPE = "impossible_type"


@dataclass
class HallucinationFinding:
    """A single hallucination detection."""

    hallucination_type: HallucinationType
    description: str
    code_snippet: str
    line_number: int | None = None
    confidence: float = 0.5
    suggestion: str = ""


@dataclass
class HallucinationReport:
    """Result of scanning code for hallucinations."""

    findings: list[HallucinationFinding] = field(default_factory=list)
    risk_score: float = 0.0
    is_safe: bool = True
    total_checks: int = 0
    passed_checks: int = 0


@dataclass
class ImportCheck:
    """Result of checking whether a single import is valid."""

    module_name: str
    exists: bool = False
    version_valid: bool = True


# ── In-memory known-module sets ──────────────────────────────────────────

_known_stdlib_modules: set[str] = {
    "os", "sys", "json", "re", "math", "datetime", "collections",
    "itertools", "functools", "pathlib", "typing", "logging", "unittest",
    "hashlib", "uuid", "io", "abc", "dataclasses", "enum", "contextlib",
    "asyncio", "http", "urllib", "sqlite3", "csv", "copy", "random",
    "time", "threading",
}

_known_packages: set[str] = {
    "flask", "django", "fastapi", "sqlalchemy", "pydantic", "requests",
    "numpy", "pandas", "pytest", "httpx", "aiohttp", "celery", "redis",
    "boto3", "anthropic", "openai",
}

_scan_history: list[HallucinationReport] = []

# ── Fabricated API patterns ──────────────────────────────────────────────

_FABRICATED_APIS: list[tuple[str, str, str]] = [
    ("os", "execute_shell", "os.execute_shell does not exist; use os.system or subprocess.run"),
    ("os", "read_file", "os.read_file does not exist; use open() or pathlib.Path.read_text"),
    ("json", "parse", "json.parse does not exist in Python; use json.loads"),
    ("json", "stringify", "json.stringify does not exist in Python; use json.dumps"),
    ("requests", "fetch", "requests.fetch does not exist; use requests.get or requests.post"),
    ("math", "round", "math.round does not exist; use the built-in round()"),
    ("datetime", "now", "datetime.now does not exist at module level; use datetime.datetime.now()"),
    ("sys", "arguments", "sys.arguments does not exist; use sys.argv"),
    ("os", "env", "os.env does not exist; use os.environ"),
    ("pathlib", "join", "pathlib.join does not exist; use pathlib.Path / operator"),
]

# ── Import extraction ────────────────────────────────────────────────────

_IMPORT_RE = re.compile(
    r"^\s*(?:import\s+([\w.]+)|from\s+([\w.]+)\s+import)",
    re.MULTILINE,
)


def extract_imports(code: str) -> list[str]:
    """Parse import statements from code and return top-level module names."""
    modules: list[str] = []
    for match in _IMPORT_RE.finditer(code):
        raw = match.group(1) or match.group(2)
        if raw:
            top_level = raw.split(".")[0]
            if top_level not in modules:
                modules.append(top_level)
    return modules


def check_imports(code: str) -> list[HallucinationFinding]:
    """Verify imports against known stdlib / PyPI modules."""
    findings: list[HallucinationFinding] = []
    modules = extract_imports(code)
    lines = code.splitlines()

    for mod in modules:
        if mod in _known_stdlib_modules or mod in _known_packages:
            continue

        # Find the line number for context
        line_no: int | None = None
        snippet = ""
        for idx, line in enumerate(lines, start=1):
            if re.search(rf"\b{re.escape(mod)}\b", line) and ("import" in line):
                line_no = idx
                snippet = line.strip()
                break

        findings.append(
            HallucinationFinding(
                hallucination_type=HallucinationType.FABRICATED_IMPORT,
                description=f"Module '{mod}' is not in the known stdlib or popular packages list",
                code_snippet=snippet,
                line_number=line_no,
                confidence=0.6,
                suggestion=f"Verify that '{mod}' is a real, installable package",
            )
        )

    return findings


# ── Function-call extraction ─────────────────────────────────────────────

_CALL_RE = re.compile(r"\b(\w+)\.(\w+)\s*\(")


def extract_function_calls(code: str) -> list[tuple[str, str]]:
    """Extract (object, method) pairs from dotted call expressions."""
    return list({(m.group(1), m.group(2)) for m in _CALL_RE.finditer(code)})


def check_api_usage(code: str) -> list[HallucinationFinding]:
    """Detect calls to commonly fabricated APIs."""
    findings: list[HallucinationFinding] = []
    calls = extract_function_calls(code)
    lines = code.splitlines()

    for obj, method in calls:
        for api_obj, api_method, suggestion in _FABRICATED_APIS:
            if obj == api_obj and method == api_method:
                line_no: int | None = None
                snippet = ""
                pattern = f"{obj}.{method}"
                for idx, line in enumerate(lines, start=1):
                    if pattern in line:
                        line_no = idx
                        snippet = line.strip()
                        break

                findings.append(
                    HallucinationFinding(
                        hallucination_type=HallucinationType.NONEXISTENT_API,
                        description=f"'{obj}.{method}' is a commonly fabricated API",
                        code_snippet=snippet,
                        line_number=line_no,
                        confidence=0.85,
                        suggestion=suggestion,
                    )
                )
    return findings


# ── Variable consistency ─────────────────────────────────────────────────

_ASSIGN_RE = re.compile(r"\b(\w+)\s*=[^=]")
_NAME_RE = re.compile(r"\b(\w+)\b")
_PYTHON_BUILTINS: set[str] = {
    "True", "False", "None", "print", "len", "range", "int", "str", "float",
    "list", "dict", "set", "tuple", "bool", "type", "super", "isinstance",
    "issubclass", "hasattr", "getattr", "setattr", "delattr", "enumerate",
    "zip", "map", "filter", "sorted", "reversed", "any", "all", "min", "max",
    "sum", "abs", "round", "open", "input", "id", "hash", "repr", "format",
    "property", "staticmethod", "classmethod", "object", "Exception",
    "ValueError", "TypeError", "KeyError", "IndexError", "AttributeError",
    "RuntimeError", "StopIteration", "NotImplementedError", "ImportError",
    "OSError", "FileNotFoundError", "self", "cls", "__name__", "__file__",
    "__init__", "__main__",
}
_PYTHON_KEYWORDS: set[str] = {
    "if", "else", "elif", "for", "while", "in", "not", "and", "or", "is",
    "with", "as", "try", "except", "finally", "raise", "return", "yield",
    "break", "continue", "pass", "def", "class", "import", "from", "global",
    "nonlocal", "lambda", "del", "assert", "async", "await",
}


def check_variable_consistency(code: str) -> list[HallucinationFinding]:
    """Detect variables that appear to be used before assignment.

    This is a lightweight heuristic check, not a full scope analysis.
    It walks lines top-to-bottom, tracking assigned names and flagging
    names that appear on the right-hand side of an expression before
    being assigned on the left.
    """
    findings: list[HallucinationFinding] = []
    assigned: set[str] = set()
    lines = code.splitlines()

    # Pre-populate with imports and function/class definitions
    imports = extract_imports(code)
    assigned.update(imports)

    for idx, line in enumerate(lines, start=1):
        stripped = line.strip()
        # Skip blank lines, comments, decorators, and structural keywords
        if not stripped or stripped.startswith("#") or stripped.startswith("@"):
            continue
        if stripped.startswith(("def ", "class ")):
            # Capture the function/class name
            name_match = re.match(r"(?:def|class)\s+(\w+)", stripped)
            if name_match:
                assigned.add(name_match.group(1))
            continue
        if stripped.startswith(("import ", "from ")):
            continue

        # Record assignments on this line
        for m in _ASSIGN_RE.finditer(stripped):
            assigned.add(m.group(1))

        # Check for parameter-like patterns (e.g., inside for-loops)
        for_match = re.match(r"for\s+(\w+)", stripped)
        if for_match:
            assigned.add(for_match.group(1))
            continue

        # Look for names used that were never assigned
        names_on_line = set(_NAME_RE.findall(stripped))
        for name in names_on_line:
            if name in assigned:
                continue
            if name in _PYTHON_BUILTINS or name in _PYTHON_KEYWORDS:
                continue
            if name[0].isupper():
                # Likely a class name or type — skip to reduce false positives
                continue
            if len(name) <= 1:
                continue
            if name.isdigit() or name.startswith("_"):
                continue

            findings.append(
                HallucinationFinding(
                    hallucination_type=HallucinationType.PHANTOM_VARIABLE,
                    description=f"Variable '{name}' used at line {idx} but not previously assigned",
                    code_snippet=stripped,
                    line_number=idx,
                    confidence=0.5,
                    suggestion=f"Ensure '{name}' is defined or imported before use",
                )
            )
            # Mark as seen so we only report once per variable
            assigned.add(name)

    return findings


# ── Syntax validation ────────────────────────────────────────────────────


def check_syntax_validity(code: str) -> list[HallucinationFinding]:
    """Try to compile the code and report any syntax errors."""
    findings: list[HallucinationFinding] = []
    try:
        compile(code, "<generated>", "exec")
    except SyntaxError as exc:
        findings.append(
            HallucinationFinding(
                hallucination_type=HallucinationType.INVALID_SYNTAX,
                description=f"Syntax error: {exc.msg}",
                code_snippet=exc.text.strip() if exc.text else "",
                line_number=exc.lineno,
                confidence=1.0,
                suggestion="Fix the syntax error before using this code",
            )
        )
    return findings


# ── Risk score computation ───────────────────────────────────────────────

_TYPE_WEIGHTS: dict[HallucinationType, float] = {
    HallucinationType.INVALID_SYNTAX: 30.0,
    HallucinationType.FABRICATED_IMPORT: 20.0,
    HallucinationType.NONEXISTENT_API: 20.0,
    HallucinationType.PHANTOM_VARIABLE: 10.0,
    HallucinationType.INCONSISTENT_LOGIC: 15.0,
    HallucinationType.IMPOSSIBLE_TYPE: 15.0,
}


def compute_risk_score(findings: list[HallucinationFinding]) -> float:
    """Compute a weighted risk score in the range 0-100."""
    if not findings:
        return 0.0
    total = sum(
        _TYPE_WEIGHTS.get(f.hallucination_type, 10.0) * f.confidence
        for f in findings
    )
    return min(total, 100.0)


# ── Full scan ────────────────────────────────────────────────────────────

_SAFE_THRESHOLD = 30.0


def scan_code(code: str, language: str = "python") -> HallucinationReport:
    """Run all hallucination checks on the given code.

    Parameters
    ----------
    code:
        The source code to analyse.
    language:
        Programming language (currently only ``"python"`` runs full checks).

    Returns
    -------
    HallucinationReport with findings and aggregate risk score.
    """
    findings: list[HallucinationFinding] = []
    total_checks = 0

    if language == "python":
        # 1. Syntax
        total_checks += 1
        syntax_findings = check_syntax_validity(code)
        findings.extend(syntax_findings)

        # 2. Imports
        total_checks += 1
        import_findings = check_imports(code)
        findings.extend(import_findings)

        # 3. API usage
        total_checks += 1
        api_findings = check_api_usage(code)
        findings.extend(api_findings)

        # 4. Variable consistency
        total_checks += 1
        var_findings = check_variable_consistency(code)
        findings.extend(var_findings)
    else:
        # For non-Python languages we can only do syntax-level heuristics
        total_checks += 1

    risk = compute_risk_score(findings)
    passed = total_checks - min(
        total_checks,
        len({f.hallucination_type for f in findings}),
    )

    report = HallucinationReport(
        findings=findings,
        risk_score=risk,
        is_safe=risk < _SAFE_THRESHOLD,
        total_checks=total_checks,
        passed_checks=passed,
    )

    _scan_history.append(report)

    if findings:
        logger.warning(
            "Hallucination scan: %d findings, risk_score=%.1f, is_safe=%s",
            len(findings),
            risk,
            report.is_safe,
        )

    return report


# ── History & stats ──────────────────────────────────────────────────────


def get_scan_history() -> list[HallucinationReport]:
    """Return the in-memory scan history."""
    return list(_scan_history)


def get_hallucination_stats() -> dict:
    """Return aggregate statistics from scan history."""
    if not _scan_history:
        return {
            "total_scans": 0,
            "safe_scans": 0,
            "unsafe_scans": 0,
            "average_risk_score": 0.0,
            "total_findings": 0,
            "findings_by_type": {},
        }

    total = len(_scan_history)
    safe = sum(1 for r in _scan_history if r.is_safe)
    all_findings = [f for r in _scan_history for f in r.findings]
    by_type: dict[str, int] = {}
    for f in all_findings:
        by_type[f.hallucination_type.value] = by_type.get(f.hallucination_type.value, 0) + 1

    return {
        "total_scans": total,
        "safe_scans": safe,
        "unsafe_scans": total - safe,
        "average_risk_score": sum(r.risk_score for r in _scan_history) / total,
        "total_findings": len(all_findings),
        "findings_by_type": by_type,
    }


def clear_scan_history() -> None:
    """Clear the in-memory scan history (useful for tests)."""
    _scan_history.clear()


# ── JSON serialisation ───────────────────────────────────────────────────


def hallucination_report_to_json(report: HallucinationReport) -> dict:
    """Convert a HallucinationReport to a plain dict suitable for JSON."""
    return {
        "findings": [
            {
                "hallucination_type": f.hallucination_type.value,
                "description": f.description,
                "code_snippet": f.code_snippet,
                "line_number": f.line_number,
                "confidence": f.confidence,
                "suggestion": f.suggestion,
            }
            for f in report.findings
        ],
        "risk_score": report.risk_score,
        "is_safe": report.is_safe,
        "total_checks": report.total_checks,
        "passed_checks": report.passed_checks,
    }
