"""Output Schema Validator -- structured LLM output enforcement.

Validates LLM responses against predefined schemas using Pydantic-style
validation, with retry logic, error feedback for reprompting, and
generator-critic pattern support.

Key features:
- JSON schema validation with detailed error reporting
- Type coercion for common LLM output mistakes (string → int, etc.)
- Retry budget with validation error feedback to the model
- Schema registry for reusable output definitions
- Generator-critic validation pattern
- Partial output recovery from truncated responses
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

logger = logging.getLogger(__name__)


# ── Enums ────────────────────────────────────────────────────────────────

class FieldType(StrEnum):
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    ARRAY = "array"
    OBJECT = "object"
    ENUM = "enum"


class ValidationSeverity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class ValidationOutcome(StrEnum):
    VALID = "valid"
    INVALID = "invalid"
    COERCED = "coerced"
    PARTIAL = "partial"


# ── Dataclasses ──────────────────────────────────────────────────────────

@dataclass
class FieldSchema:
    """Schema definition for a single output field."""

    name: str
    field_type: FieldType
    required: bool = True
    description: str = ""
    default: object = None
    enum_values: list[str] | None = None
    min_value: float | None = None
    max_value: float | None = None
    min_length: int | None = None
    max_length: int | None = None
    pattern: str | None = None
    items_type: FieldType | None = None  # for arrays


@dataclass
class OutputSchema:
    """A complete schema for validating LLM output."""

    name: str
    description: str
    fields: list[FieldSchema]
    strict: bool = True  # reject on any error vs. coerce
    version: str = "1.0"
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class ValidationError:
    """A single validation error."""

    field: str
    message: str
    severity: ValidationSeverity = ValidationSeverity.ERROR
    expected: str = ""
    actual: str = ""


@dataclass
class ValidationResult:
    """Result of validating LLM output against a schema."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    schema_name: str = ""
    outcome: ValidationOutcome = ValidationOutcome.VALID
    errors: list[ValidationError] = field(default_factory=list)
    warnings: list[ValidationError] = field(default_factory=list)
    coercions: list[str] = field(default_factory=list)
    parsed_data: dict | None = None
    raw_output: str = ""
    attempt: int = 1
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def is_valid(self) -> bool:
        return self.outcome in (
            ValidationOutcome.VALID,
            ValidationOutcome.COERCED,
        )

    def error_feedback(self) -> str:
        """Generate a feedback prompt for the LLM to fix errors."""
        if not self.errors:
            return ""
        lines = ["Your previous output had validation errors:"]
        for err in self.errors:
            lines.append(f"- Field '{err.field}': {err.message}")
            if err.expected:
                lines.append(f"  Expected: {err.expected}")
            if err.actual:
                lines.append(f"  Got: {err.actual}")
        lines.append("Please fix these issues and respond again.")
        return "\n".join(lines)


@dataclass
class CriticResult:
    """Result of generator-critic validation."""

    generator_output: dict | None
    critic_feedback: list[str]
    is_approved: bool
    iterations: int


# ── JSON extraction ──────────────────────────────────────────────────────

def extract_json(text: str) -> dict | None:
    """Extract JSON from LLM output that may contain markdown or prose."""
    # Try direct parse first
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        pass

    # Try extracting from markdown code block
    patterns = [
        r"```json\s*\n?(.*?)\n?\s*```",
        r"```\s*\n?(.*?)\n?\s*```",
        r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}",
    ]
    for pat in patterns:
        match = re.search(pat, text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1) if "```" in pat else match.group(0))
            except (json.JSONDecodeError, TypeError, IndexError):
                continue

    # Try recovering truncated JSON
    return _recover_truncated_json(text)


def _recover_truncated_json(text: str) -> dict | None:
    """Attempt to recover truncated JSON by closing brackets."""
    # Find the start of JSON
    start = text.find("{")
    if start == -1:
        return None

    fragment = text[start:]
    # Count open/close braces
    open_braces = fragment.count("{") - fragment.count("}")
    open_brackets = fragment.count("[") - fragment.count("]")

    if open_braces > 0 or open_brackets > 0:
        # Try closing
        fragment += "]" * open_brackets
        fragment += "}" * open_braces
        try:
            return json.loads(fragment)
        except (json.JSONDecodeError, TypeError):
            pass
    return None


# ── Type coercion ────────────────────────────────────────────────────────

def _coerce_value(
    value: object,
    expected_type: FieldType,
) -> tuple[object, bool]:
    """Try to coerce a value to the expected type. Returns (value, coerced)."""
    if expected_type == FieldType.STRING:
        if not isinstance(value, str):
            return str(value), True
    elif expected_type == FieldType.INTEGER:
        if not isinstance(value, int) or isinstance(value, bool):
            try:
                return int(float(str(value))), True
            except (ValueError, TypeError):
                return value, False
    elif expected_type == FieldType.FLOAT:
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            try:
                return float(str(value)), True
            except (ValueError, TypeError):
                return value, False
    elif expected_type == FieldType.BOOLEAN:
        if not isinstance(value, bool):
            if str(value).lower() in ("true", "1", "yes"):
                return True, True
            elif str(value).lower() in ("false", "0", "no"):
                return False, True
            return value, False
    elif expected_type == FieldType.ARRAY:
        if not isinstance(value, list):
            if isinstance(value, str):
                try:
                    parsed = json.loads(value)
                    if isinstance(parsed, list):
                        return parsed, True
                except (json.JSONDecodeError, TypeError):
                    pass
            return value, False
    elif expected_type == FieldType.OBJECT:
        if not isinstance(value, dict) and isinstance(value, str):
            try:
                parsed = json.loads(value)
                if isinstance(parsed, dict):
                    return parsed, True
            except (json.JSONDecodeError, TypeError):
                pass
            return value, False
        elif not isinstance(value, dict):
            return value, False

    return value, False


# ── Schema Registry ──────────────────────────────────────────────────────

class SchemaRegistry:
    """Registry of reusable output schemas."""

    def __init__(self):
        self._schemas: dict[str, OutputSchema] = {}

    def register(self, schema: OutputSchema) -> None:
        self._schemas[schema.name] = schema

    def get(self, name: str) -> OutputSchema | None:
        return self._schemas.get(name)

    def list_schemas(self) -> list[str]:
        return list(self._schemas.keys())

    def remove(self, name: str) -> bool:
        return self._schemas.pop(name, None) is not None

    @property
    def count(self) -> int:
        return len(self._schemas)


# ── Output Schema Validator ──────────────────────────────────────────────

class OutputSchemaValidator:
    """Validates LLM outputs against schemas with coercion and retry support."""

    def __init__(self):
        self.registry = SchemaRegistry()
        self._history: list[ValidationResult] = []

    def validate(
        self,
        raw_output: str,
        schema: OutputSchema,
        attempt: int = 1,
    ) -> ValidationResult:
        """Validate raw LLM output against a schema."""
        result = ValidationResult(
            schema_name=schema.name,
            raw_output=raw_output,
            attempt=attempt,
        )

        # 1. Extract JSON
        data = extract_json(raw_output)
        if data is None:
            result.outcome = ValidationOutcome.INVALID
            result.errors.append(ValidationError(
                field="$root",
                message="Could not parse JSON from output",
                expected="valid JSON object",
                actual=raw_output[:100],
            ))
            self._history.append(result)
            return result

        # 2. Validate each field
        errors: list[ValidationError] = []
        warnings: list[ValidationError] = []
        coercions: list[str] = []

        for fld in schema.fields:
            value = data.get(fld.name)

            # Required check
            if value is None:
                if fld.required:
                    if fld.default is not None:
                        data[fld.name] = fld.default
                        coercions.append(
                            f"{fld.name}: used default {fld.default}"
                        )
                    else:
                        errors.append(ValidationError(
                            field=fld.name,
                            message="Required field is missing",
                            expected=fld.field_type,
                        ))
                continue

            # Type check with coercion
            if not self._type_matches(value, fld.field_type):
                if not schema.strict:
                    coerced_val, did_coerce = _coerce_value(
                        value, fld.field_type
                    )
                    if did_coerce:
                        data[fld.name] = coerced_val
                        coercions.append(
                            f"{fld.name}: {type(value).__name__} → "
                            f"{fld.field_type}"
                        )
                        value = coerced_val
                    else:
                        errors.append(ValidationError(
                            field=fld.name,
                            message="Type mismatch (coercion failed)",
                            severity=ValidationSeverity.ERROR,
                            expected=fld.field_type,
                            actual=type(value).__name__,
                        ))
                        continue
                else:
                    errors.append(ValidationError(
                        field=fld.name,
                        message=f"Expected {fld.field_type}, got {type(value).__name__}",
                        severity=ValidationSeverity.ERROR,
                        expected=fld.field_type,
                        actual=type(value).__name__,
                    ))
                    continue

            # Enum check
            if fld.enum_values and value not in fld.enum_values:
                errors.append(ValidationError(
                    field=fld.name,
                    message="Value not in allowed enum",
                    expected=str(fld.enum_values),
                    actual=str(value),
                ))

            # Range check
            if (
                fld.min_value is not None
                and isinstance(value, (int, float))
                and value < fld.min_value
            ):
                errors.append(ValidationError(
                    field=fld.name,
                    message=f"Value below minimum ({fld.min_value})",
                    expected=f">= {fld.min_value}",
                    actual=str(value),
                ))

            if (
                fld.max_value is not None
                and isinstance(value, (int, float))
                and value > fld.max_value
            ):
                errors.append(ValidationError(
                    field=fld.name,
                    message=f"Value above maximum ({fld.max_value})",
                    expected=f"<= {fld.max_value}",
                    actual=str(value),
                ))

            # String length check
            if isinstance(value, str):
                if fld.min_length is not None and len(value) < fld.min_length:
                    errors.append(ValidationError(
                        field=fld.name,
                        message="String too short",
                        expected=f">= {fld.min_length} chars",
                        actual=f"{len(value)} chars",
                    ))
                if fld.max_length is not None and len(value) > fld.max_length:
                    warnings.append(ValidationError(
                        field=fld.name,
                        message="String too long",
                        severity=ValidationSeverity.WARNING,
                        expected=f"<= {fld.max_length} chars",
                        actual=f"{len(value)} chars",
                    ))

            # Pattern check
            if (
                fld.pattern
                and isinstance(value, str)
                and not re.match(fld.pattern, value)
            ):
                errors.append(ValidationError(
                    field=fld.name,
                    message="Value doesn't match pattern",
                    expected=fld.pattern,
                    actual=value,
                ))

        # 3. Determine outcome
        if errors:
            result.outcome = ValidationOutcome.INVALID
        elif coercions:
            result.outcome = ValidationOutcome.COERCED
        else:
            result.outcome = ValidationOutcome.VALID

        result.errors = errors
        result.warnings = warnings
        result.coercions = coercions
        result.parsed_data = data

        self._history.append(result)
        logger.debug(
            "Validation %s: %s (attempt %d, %d errors, %d coercions)",
            result.outcome,
            schema.name,
            attempt,
            len(errors),
            len(coercions),
        )
        return result

    def validate_with_retry(
        self,
        raw_output: str,
        schema: OutputSchema,
        max_retries: int = 3,
        reprompt_fn: callable | None = None,
    ) -> ValidationResult:
        """Validate with retry logic, feeding errors back for reprompting."""
        result = self.validate(raw_output, schema, attempt=1)

        attempt = 1
        while not result.is_valid and attempt < max_retries:
            if reprompt_fn is None:
                break
            attempt += 1
            feedback = result.error_feedback()
            new_output = reprompt_fn(feedback)
            result = self.validate(new_output, schema, attempt=attempt)

        return result

    def critic_validate(
        self,
        data: dict,
        schema: OutputSchema,
        critic_fn: callable,
        max_iterations: int = 2,
    ) -> CriticResult:
        """Generator-critic pattern: validate data via a critic function."""
        feedback: list[str] = []
        current = data
        approved = False

        iterations_run = 0
        for _ in range(max_iterations):
            iterations_run += 1
            issues = critic_fn(current, schema)
            if not issues:
                approved = True
                break
            feedback.extend(issues)

        return CriticResult(
            generator_output=current,
            critic_feedback=feedback,
            is_approved=approved,
            iterations=iterations_run,
        )

    @staticmethod
    def _type_matches(value: object, expected: FieldType) -> bool:
        """Check if a value matches the expected type."""
        if expected == FieldType.STRING:
            return isinstance(value, str)
        elif expected == FieldType.INTEGER:
            return isinstance(value, int) and not isinstance(value, bool)
        elif expected == FieldType.FLOAT:
            return isinstance(value, (int, float)) and not isinstance(value, bool)
        elif expected == FieldType.BOOLEAN:
            return isinstance(value, bool)
        elif expected == FieldType.ARRAY:
            return isinstance(value, list)
        elif expected == FieldType.OBJECT:
            return isinstance(value, dict)
        elif expected == FieldType.ENUM:
            return isinstance(value, str)
        return False

    # ── Stats ───────────────────────────────────────────────────────

    def stats(self) -> dict:
        """Return validation statistics."""
        total = len(self._history)
        if total == 0:
            return {
                "total_validations": 0,
                "valid": 0,
                "invalid": 0,
                "coerced": 0,
                "avg_attempts": 0.0,
            }

        valid = sum(
            1 for r in self._history
            if r.outcome == ValidationOutcome.VALID
        )
        invalid = sum(
            1 for r in self._history
            if r.outcome == ValidationOutcome.INVALID
        )
        coerced = sum(
            1 for r in self._history
            if r.outcome == ValidationOutcome.COERCED
        )
        avg_attempts = sum(r.attempt for r in self._history) / total

        return {
            "total_validations": total,
            "valid": valid,
            "invalid": invalid,
            "coerced": coerced,
            "success_rate_pct": round(
                (valid + coerced) / total * 100, 1
            ),
            "avg_attempts": round(avg_attempts, 2),
        }

    def clear(self):
        """Clear validation history."""
        self._history.clear()
