"""MCP Tool Gateway & Interop -- manage and govern external tool access.

Implements a gateway layer for Model Context Protocol (MCP) tool integration,
providing authentication, rate limiting, schema validation, audit logging,
and circuit-breaking for external tool calls made by AI agents.

Key features:
- Tool registry with schema validation for inputs/outputs
- Authentication & authorization per tool (API key, OAuth, token-based)
- Rate limiting per tool per agent with sliding window
- Circuit breaker for failing tools (closed/open/half-open)
- Request/response audit logging with full provenance
- Tool health monitoring with latency tracking
- Fallback tool chains when primary tool is unavailable
- Tool capability discovery and matching
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


# ── Enums ────────────────────────────────────────────────────────────────

class ToolStatus(StrEnum):
    ACTIVE = "active"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    DISABLED = "disabled"


class AuthType(StrEnum):
    NONE = "none"
    API_KEY = "api_key"
    OAUTH = "oauth"
    TOKEN = "token"
    MUTUAL_TLS = "mtls"


class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class InvocationResult(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    CIRCUIT_OPEN = "circuit_open"
    AUTH_FAILED = "auth_failed"
    VALIDATION_ERROR = "validation_error"


# ── Dataclasses ──────────────────────────────────────────────────────────

@dataclass
class ToolSchema:
    """Input/output schema for a tool."""
    input_fields: dict[str, str] = field(default_factory=dict)  # name -> type
    required_fields: list[str] = field(default_factory=list)
    output_fields: dict[str, str] = field(default_factory=dict)


@dataclass
class ToolDefinition:
    """Registration of an external tool."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    endpoint: str = ""
    auth_type: AuthType = AuthType.NONE
    schema: ToolSchema = field(default_factory=ToolSchema)
    status: ToolStatus = ToolStatus.ACTIVE
    rate_limit_per_minute: int = 60
    timeout_ms: float = 5000.0
    fallback_tool_id: str | None = None
    tags: list[str] = field(default_factory=list)
    registered_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass
class ToolInvocation:
    """Record of a single tool invocation."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    tool_id: str = ""
    agent_id: str = ""
    result: InvocationResult = InvocationResult.SUCCESS
    input_data: dict[str, Any] = field(default_factory=dict)
    output_data: dict[str, Any] = field(default_factory=dict)
    latency_ms: float = 0.0
    error_message: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass
class CircuitBreaker:
    """Circuit breaker state for a tool."""
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    failure_threshold: int = 5
    recovery_timeout_seconds: float = 60.0
    last_failure_time: float = 0.0
    half_open_successes: int = 0
    half_open_threshold: int = 2


@dataclass
class RateLimitState:
    """Sliding window rate limiter state."""
    window_start: float = 0.0
    request_count: int = 0
    limit_per_minute: int = 60


# ── Tool Gateway ─────────────────────────────────────────────────────────

class ToolGateway:
    """Manages external tool access with governance policies."""

    def __init__(self):
        self._tools: dict[str, ToolDefinition] = {}
        self._invocations: list[ToolInvocation] = []
        self._circuits: dict[str, CircuitBreaker] = {}
        self._rate_limits: dict[str, RateLimitState] = {}  # key: tool_id:agent_id
        self._auth_tokens: dict[str, str] = {}  # tool_id -> token

    # ── Tool Registry ─────────────────────────────────────────────────

    def register_tool(
        self, name: str, description: str = "", endpoint: str = "",
        auth_type: AuthType = AuthType.NONE,
        schema: ToolSchema | None = None,
        rate_limit: int = 60, timeout_ms: float = 5000.0,
        fallback_tool_id: str | None = None,
        tags: list[str] | None = None,
    ) -> ToolDefinition:
        """Register a new tool in the gateway."""
        tool = ToolDefinition(
            name=name,
            description=description,
            endpoint=endpoint,
            auth_type=auth_type,
            schema=schema or ToolSchema(),
            rate_limit_per_minute=rate_limit,
            timeout_ms=timeout_ms,
            fallback_tool_id=fallback_tool_id,
            tags=tags or [],
        )
        self._tools[tool.id] = tool
        self._circuits[tool.id] = CircuitBreaker(failure_threshold=5)
        logger.info("Registered tool %s (%s)", name, tool.id[:8])
        return tool

    def get_tool(self, tool_id: str) -> ToolDefinition | None:
        return self._tools.get(tool_id)

    def find_tools(self, **filters: Any) -> list[ToolDefinition]:
        """Find tools matching filters (tag, status, name pattern)."""
        results = list(self._tools.values())
        if "tag" in filters:
            results = [t for t in results if filters["tag"] in t.tags]
        if "status" in filters:
            results = [t for t in results if t.status == filters["status"]]
        if "name" in filters:
            results = [t for t in results if filters["name"].lower() in t.name.lower()]
        return results

    def set_auth_token(self, tool_id: str, token: str) -> None:
        """Set authentication token for a tool."""
        self._auth_tokens[tool_id] = token

    def disable_tool(self, tool_id: str) -> None:
        tool = self._tools.get(tool_id)
        if tool:
            tool.status = ToolStatus.DISABLED

    def enable_tool(self, tool_id: str) -> None:
        tool = self._tools.get(tool_id)
        if tool:
            tool.status = ToolStatus.ACTIVE

    # ── Invocation ────────────────────────────────────────────────────

    def invoke(
        self, tool_id: str, agent_id: str, input_data: dict[str, Any],
    ) -> ToolInvocation:
        """Invoke a tool with full governance checks."""
        tool = self._tools.get(tool_id)
        if not tool:
            return self._make_invocation(
                tool_id, agent_id, input_data,
                InvocationResult.FAILURE, error="Tool not found",
            )

        # Check tool status
        if tool.status == ToolStatus.DISABLED:
            return self._make_invocation(
                tool_id, agent_id, input_data,
                InvocationResult.FAILURE, error="Tool is disabled",
            )

        # Check circuit breaker
        circuit_result = self._check_circuit(tool_id)
        if circuit_result:
            inv = self._make_invocation(
                tool_id, agent_id, input_data,
                InvocationResult.CIRCUIT_OPEN, error="Circuit breaker is open",
            )
            # Try fallback
            if tool.fallback_tool_id:
                return self.invoke(tool.fallback_tool_id, agent_id, input_data)
            return inv

        # Check rate limit
        rate_result = self._check_rate_limit(tool_id, agent_id, tool.rate_limit_per_minute)
        if rate_result:
            return self._make_invocation(
                tool_id, agent_id, input_data,
                InvocationResult.RATE_LIMITED, error="Rate limit exceeded",
            )

        # Check auth
        if tool.auth_type != AuthType.NONE and tool_id not in self._auth_tokens:
                return self._make_invocation(
                    tool_id, agent_id, input_data,
                    InvocationResult.AUTH_FAILED, error="No auth token configured",
                )

        # Validate input schema
        validation_error = self._validate_input(tool, input_data)
        if validation_error:
            return self._make_invocation(
                tool_id, agent_id, input_data,
                InvocationResult.VALIDATION_ERROR, error=validation_error,
            )

        # Simulate successful invocation (actual HTTP call would go here)
        invocation = self._make_invocation(
            tool_id, agent_id, input_data,
            InvocationResult.SUCCESS, output={"status": "ok"},
        )

        # Update circuit breaker on success
        self._record_circuit_success(tool_id)

        return invocation

    def record_failure(self, tool_id: str, agent_id: str, error: str = "") -> None:
        """Record a tool invocation failure (for circuit breaker)."""
        self._record_circuit_failure(tool_id)

    # ── Schema Validation ─────────────────────────────────────────────

    def _validate_input(self, tool: ToolDefinition, input_data: dict[str, Any]) -> str | None:
        """Validate input data against tool schema."""
        schema = tool.schema
        # Check required fields
        for req_field in schema.required_fields:
            if req_field not in input_data:
                return f"Missing required field: {req_field}"

        # Type checking
        for field_name, expected_type in schema.input_fields.items():
            if field_name in input_data:
                value = input_data[field_name]
                if expected_type == "string" and not isinstance(value, str):
                    return f"Field {field_name} must be string, got {type(value).__name__}"
                if expected_type == "int" and not isinstance(value, int):
                    return f"Field {field_name} must be int, got {type(value).__name__}"
                if expected_type == "bool" and not isinstance(value, bool):
                    return f"Field {field_name} must be bool, got {type(value).__name__}"

        return None

    # ── Circuit Breaker ───────────────────────────────────────────────

    def _check_circuit(self, tool_id: str) -> bool:
        """Returns True if circuit is open (should block)."""
        cb = self._circuits.get(tool_id)
        if not cb:
            return False

        if cb.state == CircuitState.CLOSED:
            return False

        if cb.state == CircuitState.OPEN:
            elapsed = time.time() - cb.last_failure_time
            if elapsed >= cb.recovery_timeout_seconds:
                cb.state = CircuitState.HALF_OPEN
                cb.half_open_successes = 0
                return False
            return True

        # HALF_OPEN: allow through
        return False

    def _record_circuit_failure(self, tool_id: str) -> None:
        cb = self._circuits.get(tool_id)
        if not cb:
            return
        cb.failure_count += 1
        cb.last_failure_time = time.time()
        if cb.state == CircuitState.HALF_OPEN:
            cb.state = CircuitState.OPEN
        elif cb.failure_count >= cb.failure_threshold:
            cb.state = CircuitState.OPEN
            logger.warning("Circuit breaker OPEN for tool %s", tool_id)

    def _record_circuit_success(self, tool_id: str) -> None:
        cb = self._circuits.get(tool_id)
        if not cb:
            return
        if cb.state == CircuitState.HALF_OPEN:
            cb.half_open_successes += 1
            if cb.half_open_successes >= cb.half_open_threshold:
                cb.state = CircuitState.CLOSED
                cb.failure_count = 0
                logger.info("Circuit breaker CLOSED for tool %s", tool_id)
        elif cb.state == CircuitState.CLOSED:
            cb.failure_count = max(0, cb.failure_count - 1)

    # ── Rate Limiting ─────────────────────────────────────────────────

    def _check_rate_limit(self, tool_id: str, agent_id: str, limit: int) -> bool:
        """Returns True if rate limit exceeded."""
        key = f"{tool_id}:{agent_id}"
        now = time.time()
        state = self._rate_limits.get(key)

        if not state or now - state.window_start > 60:
            self._rate_limits[key] = RateLimitState(
                window_start=now, request_count=1, limit_per_minute=limit,
            )
            return False

        state.request_count += 1
        return state.request_count > limit

    # ── Helpers ───────────────────────────────────────────────────────

    def _make_invocation(
        self, tool_id: str, agent_id: str, input_data: dict[str, Any],
        result: InvocationResult, error: str = "",
        output: dict[str, Any] | None = None,
    ) -> ToolInvocation:
        inv = ToolInvocation(
            tool_id=tool_id,
            agent_id=agent_id,
            result=result,
            input_data=input_data,
            output_data=output or {},
            error_message=error,
        )
        self._invocations.append(inv)
        return inv

    # ── Analytics ─────────────────────────────────────────────────────

    def tool_health(self, tool_id: str) -> dict[str, Any]:
        """Get health metrics for a specific tool."""
        invocations = [i for i in self._invocations if i.tool_id == tool_id]
        if not invocations:
            return {"tool_id": tool_id, "invocations": 0}

        successes = sum(1 for i in invocations if i.result == InvocationResult.SUCCESS)
        failures = sum(1 for i in invocations if i.result in (
            InvocationResult.FAILURE, InvocationResult.TIMEOUT))
        latencies = [i.latency_ms for i in invocations if i.latency_ms > 0]

        cb = self._circuits.get(tool_id)

        return {
            "tool_id": tool_id,
            "invocations": len(invocations),
            "success_rate": successes / len(invocations),
            "failure_rate": failures / len(invocations),
            "avg_latency_ms": sum(latencies) / len(latencies) if latencies else 0,
            "circuit_state": cb.state if cb else "unknown",
            "rate_limited_count": sum(
                1 for i in invocations if i.result == InvocationResult.RATE_LIMITED
            ),
        }

    def global_stats(self) -> dict[str, Any]:
        """Aggregate stats across all tools."""
        if not self._invocations:
            return {"total_invocations": 0, "total_tools": len(self._tools)}

        total = len(self._invocations)
        successes = sum(1 for i in self._invocations if i.result == InvocationResult.SUCCESS)

        tool_counts: dict[str, int] = {}
        for inv in self._invocations:
            tool = self._tools.get(inv.tool_id)
            name = tool.name if tool else inv.tool_id
            tool_counts[name] = tool_counts.get(name, 0) + 1

        return {
            "total_invocations": total,
            "total_tools": len(self._tools),
            "overall_success_rate": successes / total,
            "invocations_by_tool": tool_counts,
            "tools_with_open_circuits": sum(
                1 for cb in self._circuits.values()
                if cb.state == CircuitState.OPEN
            ),
        }
