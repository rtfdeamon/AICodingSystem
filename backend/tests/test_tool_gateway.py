"""Tests for MCP Tool Gateway & Interop."""

from __future__ import annotations

import time

from app.quality.tool_gateway import (
    AuthType,
    CircuitState,
    InvocationResult,
    ToolGateway,
    ToolSchema,
    ToolStatus,
)

# ── Tool Registry ─────────────────────────────────────────────────────────

class TestToolRegistry:
    def test_register_tool(self):
        gw = ToolGateway()
        tool = gw.register_tool("code-search", description="Search code", endpoint="https://api.search.com")
        assert tool.name == "code-search"
        assert tool.status == ToolStatus.ACTIVE

    def test_get_tool(self):
        gw = ToolGateway()
        tool = gw.register_tool("test")
        assert gw.get_tool(tool.id) is not None

    def test_get_missing_tool(self):
        gw = ToolGateway()
        assert gw.get_tool("missing") is None

    def test_find_by_tag(self):
        gw = ToolGateway()
        gw.register_tool("search", tags=["code", "search"])
        gw.register_tool("lint", tags=["quality"])
        results = gw.find_tools(tag="code")
        assert len(results) == 1
        assert results[0].name == "search"

    def test_find_by_status(self):
        gw = ToolGateway()
        gw.register_tool("active-tool")
        t2 = gw.register_tool("disabled-tool")
        gw.disable_tool(t2.id)
        results = gw.find_tools(status=ToolStatus.ACTIVE)
        assert len(results) == 1

    def test_find_by_name(self):
        gw = ToolGateway()
        gw.register_tool("code-search")
        gw.register_tool("lint-runner")
        results = gw.find_tools(name="search")
        assert len(results) == 1

    def test_disable_enable_tool(self):
        gw = ToolGateway()
        tool = gw.register_tool("test")
        gw.disable_tool(tool.id)
        assert gw.get_tool(tool.id).status == ToolStatus.DISABLED
        gw.enable_tool(tool.id)
        assert gw.get_tool(tool.id).status == ToolStatus.ACTIVE


# ── Invocation ────────────────────────────────────────────────────────────

class TestInvocation:
    def test_successful_invocation(self):
        gw = ToolGateway()
        tool = gw.register_tool("test")
        inv = gw.invoke(tool.id, "agent-1", {"query": "hello"})
        assert inv.result == InvocationResult.SUCCESS

    def test_invoke_missing_tool(self):
        gw = ToolGateway()
        inv = gw.invoke("missing", "agent-1", {})
        assert inv.result == InvocationResult.FAILURE
        assert "not found" in inv.error_message

    def test_invoke_disabled_tool(self):
        gw = ToolGateway()
        tool = gw.register_tool("test")
        gw.disable_tool(tool.id)
        inv = gw.invoke(tool.id, "agent-1", {})
        assert inv.result == InvocationResult.FAILURE
        assert "disabled" in inv.error_message


# ── Authentication ────────────────────────────────────────────────────────

class TestAuthentication:
    def test_auth_required_no_token(self):
        gw = ToolGateway()
        tool = gw.register_tool("secure", auth_type=AuthType.API_KEY)
        inv = gw.invoke(tool.id, "agent-1", {})
        assert inv.result == InvocationResult.AUTH_FAILED

    def test_auth_with_token(self):
        gw = ToolGateway()
        tool = gw.register_tool("secure", auth_type=AuthType.API_KEY)
        gw.set_auth_token(tool.id, "sk-test-token")
        inv = gw.invoke(tool.id, "agent-1", {})
        assert inv.result == InvocationResult.SUCCESS

    def test_no_auth_required(self):
        gw = ToolGateway()
        tool = gw.register_tool("public", auth_type=AuthType.NONE)
        inv = gw.invoke(tool.id, "agent-1", {})
        assert inv.result == InvocationResult.SUCCESS


# ── Schema Validation ─────────────────────────────────────────────────────

class TestSchemaValidation:
    def test_missing_required_field(self):
        gw = ToolGateway()
        schema = ToolSchema(
            input_fields={"query": "string"},
            required_fields=["query"],
        )
        tool = gw.register_tool("search", schema=schema)
        inv = gw.invoke(tool.id, "agent-1", {})
        assert inv.result == InvocationResult.VALIDATION_ERROR
        assert "query" in inv.error_message

    def test_valid_required_field(self):
        gw = ToolGateway()
        schema = ToolSchema(
            input_fields={"query": "string"},
            required_fields=["query"],
        )
        tool = gw.register_tool("search", schema=schema)
        inv = gw.invoke(tool.id, "agent-1", {"query": "hello"})
        assert inv.result == InvocationResult.SUCCESS

    def test_wrong_type(self):
        gw = ToolGateway()
        schema = ToolSchema(
            input_fields={"count": "int"},
            required_fields=[],
        )
        tool = gw.register_tool("counter", schema=schema)
        inv = gw.invoke(tool.id, "agent-1", {"count": "not_an_int"})
        assert inv.result == InvocationResult.VALIDATION_ERROR

    def test_bool_type_check(self):
        gw = ToolGateway()
        schema = ToolSchema(input_fields={"flag": "bool"})
        tool = gw.register_tool("flag-tool", schema=schema)
        inv = gw.invoke(tool.id, "agent-1", {"flag": "true"})
        assert inv.result == InvocationResult.VALIDATION_ERROR


# ── Rate Limiting ─────────────────────────────────────────────────────────

class TestRateLimiting:
    def test_rate_limit_exceeded(self):
        gw = ToolGateway()
        tool = gw.register_tool("test", rate_limit=3)
        for _ in range(3):
            inv = gw.invoke(tool.id, "agent-1", {})
            assert inv.result == InvocationResult.SUCCESS
        inv = gw.invoke(tool.id, "agent-1", {})
        assert inv.result == InvocationResult.RATE_LIMITED

    def test_rate_limit_per_agent(self):
        gw = ToolGateway()
        tool = gw.register_tool("test", rate_limit=2)
        gw.invoke(tool.id, "agent-1", {})
        gw.invoke(tool.id, "agent-1", {})
        # agent-2 has its own limit
        inv = gw.invoke(tool.id, "agent-2", {})
        assert inv.result == InvocationResult.SUCCESS


# ── Circuit Breaker ───────────────────────────────────────────────────────

class TestCircuitBreaker:
    def test_circuit_opens_after_failures(self):
        gw = ToolGateway()
        tool = gw.register_tool("test")
        cb = gw._circuits[tool.id]
        cb.failure_threshold = 3
        for _ in range(3):
            gw.record_failure(tool.id, "agent-1", "error")
        assert cb.state == CircuitState.OPEN

    def test_circuit_open_blocks_invocations(self):
        gw = ToolGateway()
        tool = gw.register_tool("test")
        cb = gw._circuits[tool.id]
        cb.failure_threshold = 2
        gw.record_failure(tool.id, "agent-1")
        gw.record_failure(tool.id, "agent-1")
        inv = gw.invoke(tool.id, "agent-1", {})
        assert inv.result == InvocationResult.CIRCUIT_OPEN

    def test_circuit_half_open_after_timeout(self):
        gw = ToolGateway()
        tool = gw.register_tool("test")
        cb = gw._circuits[tool.id]
        cb.failure_threshold = 1
        cb.recovery_timeout_seconds = 0.01
        gw.record_failure(tool.id, "agent-1")
        assert cb.state == CircuitState.OPEN
        time.sleep(0.02)
        inv = gw.invoke(tool.id, "agent-1", {})
        assert inv.result == InvocationResult.SUCCESS
        assert cb.state in (CircuitState.HALF_OPEN, CircuitState.CLOSED)

    def test_circuit_closes_after_half_open_successes(self):
        gw = ToolGateway()
        tool = gw.register_tool("test")
        cb = gw._circuits[tool.id]
        cb.state = CircuitState.HALF_OPEN
        cb.half_open_threshold = 2
        gw.invoke(tool.id, "agent-1", {})
        gw.invoke(tool.id, "agent-1", {})
        assert cb.state == CircuitState.CLOSED


# ── Fallback ──────────────────────────────────────────────────────────────

class TestFallback:
    def test_fallback_on_circuit_open(self):
        gw = ToolGateway()
        fallback = gw.register_tool("fallback-search")
        primary = gw.register_tool("primary-search", fallback_tool_id=fallback.id)
        cb = gw._circuits[primary.id]
        cb.failure_threshold = 1
        gw.record_failure(primary.id, "agent-1")
        inv = gw.invoke(primary.id, "agent-1", {"q": "test"})
        assert inv.result == InvocationResult.SUCCESS
        assert inv.tool_id == fallback.id


# ── Health & Analytics ────────────────────────────────────────────────────

class TestHealthAnalytics:
    def test_tool_health(self):
        gw = ToolGateway()
        tool = gw.register_tool("test")
        gw.invoke(tool.id, "agent-1", {})
        gw.invoke(tool.id, "agent-1", {})
        health = gw.tool_health(tool.id)
        assert health["invocations"] == 2
        assert health["success_rate"] == 1.0

    def test_tool_health_empty(self):
        gw = ToolGateway()
        health = gw.tool_health("missing")
        assert health["invocations"] == 0

    def test_global_stats(self):
        gw = ToolGateway()
        tool = gw.register_tool("test")
        gw.invoke(tool.id, "agent-1", {})
        stats = gw.global_stats()
        assert stats["total_invocations"] == 1
        assert stats["total_tools"] == 1
        assert stats["overall_success_rate"] == 1.0

    def test_global_stats_empty(self):
        gw = ToolGateway()
        stats = gw.global_stats()
        assert stats["total_invocations"] == 0
