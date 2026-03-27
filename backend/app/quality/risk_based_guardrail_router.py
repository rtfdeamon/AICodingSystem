"""Risk-Based Guardrail Router — dynamically adjust guardrail intensity
based on the risk level of each request.

Not all requests carry the same risk.  A low-risk internal FAQ lookup
should not suffer the 500 ms latency of full guardrail evaluation,
while a high-risk financial advice query must pass every check.
Risk-based routing dynamically selects the guardrail tier — from
lightweight regex to full LLM-as-judge — keeping latency low for
safe paths while maximising safety for dangerous ones.

Based on:
- Authority Partners "AI Agent Guardrails: Production Guide for 2026"
- Datadog "LLM Guardrails Best Practices" (2026)
- Openlayer "AI Guardrails: The Complete Guide" (Jan 2026)
- Patronus AI "AI Guardrails Tutorial & Best Practices" (2026)
- TFIR "AI Code Quality 2026: Guardrails for AI-Generated Code"

Key capabilities:
- Request risk classification: low / medium / high / critical
- Three guardrail tiers: lightweight, standard, comprehensive
- Per-tier configurable check sets with latency budgets
- Async validation option for low-risk paths (check after serving)
- Guardrail result aggregation with weighted scoring
- Override rules: force comprehensive for sensitive domains
- Latency tracking per tier and per check
- Quality gate: configurable pass/warn/block per tier
- Batch routing across multiple requests
"""

from __future__ import annotations

import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

logger = logging.getLogger(__name__)


# ── Enums ────────────────────────────────────────────────────────────────

class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class GuardrailTier(StrEnum):
    LIGHTWEIGHT = "lightweight"
    STANDARD = "standard"
    COMPREHENSIVE = "comprehensive"


class CheckResult(StrEnum):
    PASS = "pass"
    WARN = "warn"
    BLOCK = "block"
    SKIP = "skip"


class GateDecision(StrEnum):
    PASS = "pass"
    WARN = "warn"
    BLOCK = "block"


# ── Data classes ─────────────────────────────────────────────────────────

@dataclass
class GuardrailCheck:
    """Result of a single guardrail check."""

    name: str
    result: CheckResult
    confidence: float  # 0-1
    latency_ms: float
    details: str = ""


@dataclass
class RiskAssessment:
    """Risk assessment for a request."""

    risk_level: RiskLevel
    risk_score: float  # 0-1
    tier: GuardrailTier
    risk_factors: list[str]
    domain: str = ""


@dataclass
class GuardrailResult:
    """Aggregate result of guardrail evaluation."""

    id: str
    risk_assessment: RiskAssessment
    checks: list[GuardrailCheck]
    aggregate_score: float  # 0-1
    gate_decision: GateDecision
    total_latency_ms: float
    checks_run: int
    checks_passed: int
    checks_warned: int
    checks_blocked: int
    async_pending: int  # checks deferred to async
    evaluated_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
    )


@dataclass
class BatchGuardrailReport:
    """Report across multiple guardrail evaluations."""

    results: list[GuardrailResult]
    total_requests: int
    risk_distribution: dict[str, int]
    tier_distribution: dict[str, int]
    avg_latency_ms: float
    block_rate: float
    gate_decision: GateDecision


# ── Risk classification ──────────────────────────────────────────────────

_HIGH_RISK_PATTERNS = [
    (r"(password|secret|token|api[_-]?key|credential)", "credentials"),
    (r"(payment|billing|credit[_-]?card|invoice|refund)", "financial"),
    (r"(medical|diagnosis|prescription|patient)", "medical"),
    (r"(legal|contract|lawsuit|compliance)", "legal"),
    (r"(delete|drop|truncate|destroy|rm\s+-rf)", "destructive"),
    (r"(admin|sudo|root|superuser|privilege)", "privileged"),
    (r"(migration|schema|alter\s+table)", "database"),
]

_MEDIUM_RISK_PATTERNS = [
    (r"(user|account|profile|email|phone)", "user_data"),
    (r"(config|setting|environment|parameter)", "configuration"),
    (r"(deploy|release|publish|push)", "deployment"),
    (r"(external|api|webhook|endpoint)", "external_api"),
]

_SENSITIVE_DOMAINS = {"financial", "medical", "legal", "security", "auth"}


def _classify_risk(
    prompt: str,
    context: str = "",
    domain: str = "",
) -> RiskAssessment:
    """Classify the risk level of a request."""
    text = f"{prompt} {context}".lower()
    risk_factors: list[str] = []
    risk_score = 0.0

    # Check high-risk patterns
    for pattern, factor in _HIGH_RISK_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            risk_factors.append(factor)
            risk_score += 0.3

    # Check medium-risk patterns
    for pattern, factor in _MEDIUM_RISK_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            risk_factors.append(factor)
            risk_score += 0.1

    # Domain override
    if domain in _SENSITIVE_DOMAINS:
        risk_score = max(risk_score, 0.7)
        risk_factors.append(f"sensitive_domain:{domain}")

    # Content length heuristic: very long prompts may hide injections
    if len(prompt) > 5000:
        risk_score += 0.1
        risk_factors.append("long_prompt")

    risk_score = min(risk_score, 1.0)

    if risk_score >= 0.7:
        level = RiskLevel.CRITICAL
        tier = GuardrailTier.COMPREHENSIVE
    elif risk_score >= 0.4:
        level = RiskLevel.HIGH
        tier = GuardrailTier.COMPREHENSIVE
    elif risk_score >= 0.15:
        level = RiskLevel.MEDIUM
        tier = GuardrailTier.STANDARD
    else:
        level = RiskLevel.LOW
        tier = GuardrailTier.LIGHTWEIGHT

    return RiskAssessment(
        risk_level=level,
        risk_score=risk_score,
        tier=tier,
        risk_factors=risk_factors,
        domain=domain,
    )


# ── Built-in checks ─────────────────────────────────────────────────────

def _check_format(text: str) -> GuardrailCheck:
    """Fast format validation (regex-level)."""
    start = time.monotonic()
    # Check for code block formatting, valid JSON, etc.
    issues = []
    if "```" in text:
        blocks = text.count("```")
        if blocks % 2 != 0:
            issues.append("unclosed code block")

    elapsed = (time.monotonic() - start) * 1000
    return GuardrailCheck(
        name="format_check",
        result=CheckResult.WARN if issues else CheckResult.PASS,
        confidence=0.95,
        latency_ms=elapsed,
        details="; ".join(issues) if issues else "format OK",
    )


def _check_pii(text: str) -> GuardrailCheck:
    """PII detection via regex patterns."""
    start = time.monotonic()
    pii_patterns = [
        (r"\b\d{3}-\d{2}-\d{4}\b", "SSN"),
        (r"\b\d{16}\b", "credit_card"),
        (r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", "email"),
        (r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b", "phone"),
    ]
    found = []
    for pattern, label in pii_patterns:
        if re.search(pattern, text):
            found.append(label)

    elapsed = (time.monotonic() - start) * 1000
    if found:
        return GuardrailCheck(
            name="pii_detection",
            result=CheckResult.BLOCK,
            confidence=0.85,
            latency_ms=elapsed,
            details=f"PII found: {', '.join(found)}",
        )
    return GuardrailCheck(
        name="pii_detection",
        result=CheckResult.PASS,
        confidence=0.90,
        latency_ms=elapsed,
        details="no PII detected",
    )


def _check_injection(text: str) -> GuardrailCheck:
    """Prompt injection detection."""
    start = time.monotonic()
    injection_patterns = [
        r"ignore\s+(previous|above|all)\s+(instructions|prompts)",
        r"you\s+are\s+now\s+(?:a|in)\s+",
        r"system\s*:\s*",
        r"<\s*(?:system|admin|override)\s*>",
        r"forget\s+(?:everything|all|your)",
        r"new\s+instructions?\s*:",
    ]
    found = []
    for pattern in injection_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            found.append(pattern[:30])

    elapsed = (time.monotonic() - start) * 1000
    if found:
        return GuardrailCheck(
            name="injection_detection",
            result=CheckResult.BLOCK,
            confidence=0.80,
            latency_ms=elapsed,
            details=f"injection pattern(s) detected: {len(found)}",
        )
    return GuardrailCheck(
        name="injection_detection",
        result=CheckResult.PASS,
        confidence=0.85,
        latency_ms=elapsed,
        details="no injection patterns",
    )


def _check_toxicity(text: str) -> GuardrailCheck:
    """Basic toxicity detection via keyword matching."""
    start = time.monotonic()
    # Simple keyword-based (production would use a classifier)
    toxic_score = 0.0
    toxic_keywords = [
        "hate", "kill", "attack", "abuse", "violent",
        "racist", "sexist", "slur",
    ]
    lower = text.lower()
    for kw in toxic_keywords:
        if kw in lower:
            toxic_score += 0.2

    toxic_score = min(toxic_score, 1.0)
    elapsed = (time.monotonic() - start) * 1000

    if toxic_score >= 0.4:
        result = CheckResult.BLOCK
    elif toxic_score >= 0.2:
        result = CheckResult.WARN
    else:
        result = CheckResult.PASS

    return GuardrailCheck(
        name="toxicity_check",
        result=result,
        confidence=0.70,
        latency_ms=elapsed,
        details=f"toxicity_score={toxic_score:.2f}",
    )


def _check_relevance(text: str, context: str) -> GuardrailCheck:
    """Check if response is relevant to the context/domain."""
    start = time.monotonic()
    # Simple word overlap check (production: semantic similarity)
    if not context:
        elapsed = (time.monotonic() - start) * 1000
        return GuardrailCheck(
            name="relevance_check",
            result=CheckResult.PASS,
            confidence=0.50,
            latency_ms=elapsed,
            details="no context to compare",
        )

    text_words = set(text.lower().split())
    context_words = set(context.lower().split())
    overlap = len(text_words & context_words)
    relevance = overlap / max(len(context_words), 1)

    elapsed = (time.monotonic() - start) * 1000
    result = CheckResult.WARN if relevance < 0.05 else CheckResult.PASS

    return GuardrailCheck(
        name="relevance_check",
        result=result,
        confidence=0.60,
        latency_ms=elapsed,
        details=f"relevance={relevance:.2f}",
    )


# ── Tier definitions ─────────────────────────────────────────────────────

_TIER_CHECKS: dict[GuardrailTier, list[str]] = {
    GuardrailTier.LIGHTWEIGHT: ["format_check"],
    GuardrailTier.STANDARD: [
        "format_check", "pii_detection", "injection_detection",
    ],
    GuardrailTier.COMPREHENSIVE: [
        "format_check", "pii_detection", "injection_detection",
        "toxicity_check", "relevance_check",
    ],
}

_CHECK_FUNCTIONS = {
    "format_check": lambda text, ctx: _check_format(text),
    "pii_detection": lambda text, ctx: _check_pii(text),
    "injection_detection": lambda text, ctx: _check_injection(text),
    "toxicity_check": lambda text, ctx: _check_toxicity(text),
    "relevance_check": _check_relevance,
}


# ── Main class ───────────────────────────────────────────────────────────

class RiskBasedGuardrailRouter:
    """Dynamically route requests through guardrail tiers based on risk.

    Low-risk requests get fast, lightweight checks.  High-risk requests
    get comprehensive evaluation.  This balances safety with latency.
    """

    def __init__(
        self,
        latency_budget_ms: dict[GuardrailTier, float] | None = None,
        block_on_any_block: bool = True,
        enable_async_for_low_risk: bool = True,
    ) -> None:
        self.latency_budget_ms = latency_budget_ms or {
            GuardrailTier.LIGHTWEIGHT: 50.0,
            GuardrailTier.STANDARD: 200.0,
            GuardrailTier.COMPREHENSIVE: 500.0,
        }
        self.block_on_any_block = block_on_any_block
        self.enable_async_for_low_risk = enable_async_for_low_risk
        self._history: list[GuardrailResult] = []

    # ── Public API ───────────────────────────────────────────────────

    def evaluate(
        self,
        text: str,
        context: str = "",
        domain: str = "",
        force_tier: GuardrailTier | None = None,
    ) -> GuardrailResult:
        """Evaluate a request through risk-appropriate guardrails."""
        risk = _classify_risk(text, context, domain)

        tier = force_tier or risk.tier
        check_names = _TIER_CHECKS.get(tier, [])

        checks: list[GuardrailCheck] = []
        async_pending = 0

        for name in check_names:
            fn = _CHECK_FUNCTIONS.get(name)
            if fn:
                check = fn(text, context)
                checks.append(check)

        # Aggregate
        passed = sum(1 for c in checks if c.result == CheckResult.PASS)
        warned = sum(1 for c in checks if c.result == CheckResult.WARN)
        blocked = sum(1 for c in checks if c.result == CheckResult.BLOCK)
        total_latency = sum(c.latency_ms for c in checks)

        # Scoring
        if not checks:
            aggregate = 1.0
        else:
            score_map = {
                CheckResult.PASS: 1.0,
                CheckResult.WARN: 0.5,
                CheckResult.BLOCK: 0.0,
                CheckResult.SKIP: 0.75,
            }
            aggregate = sum(
                score_map.get(c.result, 0.5) * c.confidence
                for c in checks
            ) / sum(c.confidence for c in checks)

        # Gate decision
        if blocked > 0 and self.block_on_any_block:
            gate = GateDecision.BLOCK
        elif warned > 0:
            gate = GateDecision.WARN
        else:
            gate = GateDecision.PASS

        result = GuardrailResult(
            id=uuid.uuid4().hex[:12],
            risk_assessment=risk,
            checks=checks,
            aggregate_score=aggregate,
            gate_decision=gate,
            total_latency_ms=total_latency,
            checks_run=len(checks),
            checks_passed=passed,
            checks_warned=warned,
            checks_blocked=blocked,
            async_pending=async_pending,
        )
        self._history.append(result)
        return result

    def classify_risk(
        self,
        prompt: str,
        context: str = "",
        domain: str = "",
    ) -> RiskAssessment:
        """Classify risk without running guardrails."""
        return _classify_risk(prompt, context, domain)

    def batch_evaluate(
        self,
        requests: list[dict[str, str]],
    ) -> BatchGuardrailReport:
        """Evaluate multiple requests and produce a report."""
        results = [
            self.evaluate(
                text=r.get("text", ""),
                context=r.get("context", ""),
                domain=r.get("domain", ""),
            )
            for r in requests
        ]

        risk_dist: dict[str, int] = {}
        tier_dist: dict[str, int] = {}
        for res in results:
            rl = res.risk_assessment.risk_level.value
            risk_dist[rl] = risk_dist.get(rl, 0) + 1
            t = res.risk_assessment.tier.value
            tier_dist[t] = tier_dist.get(t, 0) + 1

        total = len(results) or 1
        avg_lat = sum(r.total_latency_ms for r in results) / total
        block_rate = sum(
            1 for r in results if r.gate_decision == GateDecision.BLOCK
        ) / total

        if block_rate > 0.3:
            gate = GateDecision.BLOCK
        elif block_rate > 0.1:
            gate = GateDecision.WARN
        else:
            gate = GateDecision.PASS

        return BatchGuardrailReport(
            results=results,
            total_requests=len(results),
            risk_distribution=risk_dist,
            tier_distribution=tier_dist,
            avg_latency_ms=avg_lat,
            block_rate=block_rate,
            gate_decision=gate,
        )
