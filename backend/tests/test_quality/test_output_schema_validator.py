"""Tests for Output Schema Validator.

Covers: JSON extraction, type coercion, schema validation,
retry logic, generator-critic, and schema registry.
"""

from __future__ import annotations

from app.quality.output_schema_validator import (
    FieldSchema,
    FieldType,
    OutputSchema,
    OutputSchemaValidator,
    SchemaRegistry,
    ValidationOutcome,
    _coerce_value,
    _recover_truncated_json,
    extract_json,
)

# ── JSON extraction ──────────────────────────────────────────────────────

class TestExtractJson:
    def test_direct_json(self):
        result = extract_json('{"name": "test", "value": 42}')
        assert result == {"name": "test", "value": 42}

    def test_markdown_code_block(self):
        text = 'Some text\n```json\n{"key": "val"}\n```\nmore text'
        result = extract_json(text)
        assert result == {"key": "val"}

    def test_bare_code_block(self):
        text = '```\n{"a": 1}\n```'
        result = extract_json(text)
        assert result == {"a": 1}

    def test_embedded_json(self):
        text = 'Here is the result: {"status": "ok"} and more'
        result = extract_json(text)
        assert result is not None
        assert result.get("status") == "ok"

    def test_no_json(self):
        result = extract_json("no json here at all")
        assert result is None

    def test_truncated_json_recovery(self):
        text = '{"name": "test", "items": [1, 2, 3'
        result = extract_json(text)
        assert result is not None


class TestRecoverTruncatedJson:
    def test_missing_closing_brace(self):
        result = _recover_truncated_json('{"a": 1')
        assert result == {"a": 1}

    def test_missing_bracket_and_brace(self):
        result = _recover_truncated_json('{"items": [1, 2')
        assert result is not None

    def test_no_json_at_all(self):
        result = _recover_truncated_json("hello world")
        assert result is None


# ── Type coercion ────────────────────────────────────────────────────────

class TestCoercion:
    def test_string_from_int(self):
        val, coerced = _coerce_value(42, FieldType.STRING)
        assert val == "42"
        assert coerced

    def test_int_from_string(self):
        val, coerced = _coerce_value("42", FieldType.INTEGER)
        assert val == 42
        assert coerced

    def test_int_from_float_string(self):
        val, coerced = _coerce_value("3.7", FieldType.INTEGER)
        assert val == 3
        assert coerced

    def test_float_from_string(self):
        val, coerced = _coerce_value("3.14", FieldType.FLOAT)
        assert val == 3.14
        assert coerced

    def test_bool_from_string_true(self):
        val, coerced = _coerce_value("true", FieldType.BOOLEAN)
        assert val is True
        assert coerced

    def test_bool_from_string_false(self):
        val, coerced = _coerce_value("false", FieldType.BOOLEAN)
        assert val is False
        assert coerced

    def test_bool_invalid(self):
        val, coerced = _coerce_value("maybe", FieldType.BOOLEAN)
        assert not coerced

    def test_array_from_string(self):
        val, coerced = _coerce_value("[1, 2, 3]", FieldType.ARRAY)
        assert val == [1, 2, 3]
        assert coerced

    def test_object_from_string(self):
        val, coerced = _coerce_value('{"a": 1}', FieldType.OBJECT)
        assert val == {"a": 1}
        assert coerced

    def test_no_coercion_needed(self):
        val, coerced = _coerce_value("hello", FieldType.STRING)
        assert not coerced

    def test_int_coercion_failure(self):
        val, coerced = _coerce_value("not-a-number", FieldType.INTEGER)
        assert not coerced


# ── Schema Registry ──────────────────────────────────────────────────────

class TestSchemaRegistry:
    def test_register_and_get(self):
        reg = SchemaRegistry()
        schema = OutputSchema(name="test", description="desc", fields=[])
        reg.register(schema)
        assert reg.get("test") is not None

    def test_get_missing(self):
        reg = SchemaRegistry()
        assert reg.get("nope") is None

    def test_list_schemas(self):
        reg = SchemaRegistry()
        reg.register(OutputSchema(name="a", description="", fields=[]))
        reg.register(OutputSchema(name="b", description="", fields=[]))
        assert sorted(reg.list_schemas()) == ["a", "b"]

    def test_remove(self):
        reg = SchemaRegistry()
        reg.register(OutputSchema(name="x", description="", fields=[]))
        assert reg.remove("x")
        assert reg.count == 0

    def test_remove_nonexistent(self):
        reg = SchemaRegistry()
        assert not reg.remove("nope")


# ── Validation ───────────────────────────────────────────────────────────

def _make_schema(strict: bool = True) -> OutputSchema:
    return OutputSchema(
        name="test_schema",
        description="Test output schema",
        strict=strict,
        fields=[
            FieldSchema(
                name="status", field_type=FieldType.STRING,
                required=True, enum_values=["ok", "error"],
            ),
            FieldSchema(
                name="count", field_type=FieldType.INTEGER,
                required=True, min_value=0, max_value=100,
            ),
            FieldSchema(
                name="score", field_type=FieldType.FLOAT,
                required=False, default=0.0,
            ),
            FieldSchema(
                name="tags", field_type=FieldType.ARRAY,
                required=False,
            ),
        ],
    )


class TestValidation:
    def test_valid_output(self):
        v = OutputSchemaValidator()
        result = v.validate(
            '{"status": "ok", "count": 5}', _make_schema()
        )
        assert result.is_valid
        assert result.outcome == ValidationOutcome.VALID

    def test_missing_required_field(self):
        v = OutputSchemaValidator()
        result = v.validate('{"status": "ok"}', _make_schema())
        assert not result.is_valid
        assert any(e.field == "count" for e in result.errors)

    def test_wrong_type_strict(self):
        v = OutputSchemaValidator()
        result = v.validate(
            '{"status": "ok", "count": "five"}', _make_schema(strict=True)
        )
        assert not result.is_valid

    def test_wrong_type_coerced(self):
        v = OutputSchemaValidator()
        result = v.validate(
            '{"status": "ok", "count": "5"}',
            _make_schema(strict=False),
        )
        assert result.is_valid
        assert result.outcome == ValidationOutcome.COERCED

    def test_enum_violation(self):
        v = OutputSchemaValidator()
        result = v.validate(
            '{"status": "unknown", "count": 5}', _make_schema()
        )
        assert not result.is_valid

    def test_min_value_violation(self):
        v = OutputSchemaValidator()
        result = v.validate(
            '{"status": "ok", "count": -1}', _make_schema()
        )
        assert not result.is_valid

    def test_max_value_violation(self):
        v = OutputSchemaValidator()
        result = v.validate(
            '{"status": "ok", "count": 999}', _make_schema()
        )
        assert not result.is_valid

    def test_default_value_used(self):
        v = OutputSchemaValidator()
        schema = _make_schema(strict=False)
        result = v.validate(
            '{"status": "ok", "count": 5}', schema
        )
        assert result.parsed_data is not None

    def test_invalid_json(self):
        v = OutputSchemaValidator()
        result = v.validate("not json at all!", _make_schema())
        assert not result.is_valid
        assert result.errors[0].field == "$root"

    def test_json_in_markdown(self):
        v = OutputSchemaValidator()
        text = '```json\n{"status": "ok", "count": 10}\n```'
        result = v.validate(text, _make_schema())
        assert result.is_valid

    def test_string_length_too_short(self):
        v = OutputSchemaValidator()
        schema = OutputSchema(
            name="len_test", description="",
            fields=[
                FieldSchema(
                    name="name", field_type=FieldType.STRING,
                    min_length=5,
                ),
            ],
        )
        result = v.validate('{"name": "ab"}', schema)
        assert not result.is_valid

    def test_pattern_validation(self):
        v = OutputSchemaValidator()
        schema = OutputSchema(
            name="pat_test", description="",
            fields=[
                FieldSchema(
                    name="email", field_type=FieldType.STRING,
                    pattern=r"^[^@]+@[^@]+\.[^@]+$",
                ),
            ],
        )
        result = v.validate('{"email": "bad-email"}', schema)
        assert not result.is_valid

    def test_pattern_valid(self):
        v = OutputSchemaValidator()
        schema = OutputSchema(
            name="pat_test", description="",
            fields=[
                FieldSchema(
                    name="email", field_type=FieldType.STRING,
                    pattern=r"^[^@]+@[^@]+\.[^@]+$",
                ),
            ],
        )
        result = v.validate('{"email": "test@example.com"}', schema)
        assert result.is_valid


class TestErrorFeedback:
    def test_error_feedback_message(self):
        v = OutputSchemaValidator()
        result = v.validate('{"status": "bad"}', _make_schema())
        feedback = result.error_feedback()
        assert "validation errors" in feedback
        assert "count" in feedback

    def test_no_feedback_when_valid(self):
        v = OutputSchemaValidator()
        result = v.validate(
            '{"status": "ok", "count": 5}', _make_schema()
        )
        assert result.error_feedback() == ""


class TestRetry:
    def test_retry_with_fix(self):
        v = OutputSchemaValidator()
        call_count = [0]

        def reprompt(feedback):
            call_count[0] += 1
            return '{"status": "ok", "count": 5}'

        result = v.validate_with_retry(
            '{"status": "bad"}',
            _make_schema(),
            max_retries=3,
            reprompt_fn=reprompt,
        )
        assert result.is_valid
        assert call_count[0] >= 1

    def test_retry_exhausted(self):
        v = OutputSchemaValidator()

        def reprompt(feedback):
            return '{"status": "still_bad"}'

        result = v.validate_with_retry(
            '{"status": "bad"}',
            _make_schema(),
            max_retries=2,
            reprompt_fn=reprompt,
        )
        assert not result.is_valid

    def test_retry_no_reprompt_fn(self):
        v = OutputSchemaValidator()
        result = v.validate_with_retry(
            '{"status": "bad"}',
            _make_schema(),
            max_retries=3,
        )
        assert not result.is_valid


class TestCriticValidation:
    def test_approved(self):
        v = OutputSchemaValidator()

        def critic(data, schema):
            return []

        result = v.critic_validate(
            {"status": "ok"}, _make_schema(),
            critic_fn=critic,
        )
        assert result.is_approved
        assert result.iterations == 1

    def test_rejected(self):
        v = OutputSchemaValidator()

        def critic(data, schema):
            return ["field 'status' invalid"]

        result = v.critic_validate(
            {"status": "bad"}, _make_schema(),
            critic_fn=critic,
            max_iterations=2,
        )
        assert not result.is_approved
        assert len(result.critic_feedback) > 0


# ── Stats ────────────────────────────────────────────────────────────────

class TestStats:
    def test_stats_empty(self):
        v = OutputSchemaValidator()
        s = v.stats()
        assert s["total_validations"] == 0

    def test_stats_with_validations(self):
        v = OutputSchemaValidator()
        v.validate('{"status": "ok", "count": 5}', _make_schema())
        v.validate('{"status": "bad"}', _make_schema())
        s = v.stats()
        assert s["total_validations"] == 2
        assert s["valid"] >= 1
        assert s["invalid"] >= 1

    def test_clear(self):
        v = OutputSchemaValidator()
        v.validate('{"status": "ok", "count": 5}', _make_schema())
        v.clear()
        assert v.stats()["total_validations"] == 0
