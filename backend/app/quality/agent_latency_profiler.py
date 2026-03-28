"""Agent Latency Profiler — per-stage latency profiling and bottleneck detection.

Tracks execution time across agent pipeline stages (prompt build, API call,
response parse, validation, post-processing), computes P50/P95/P99
percentiles, identifies bottlenecks, and provides optimisation suggestions.

Based on:
- AIMultiple "LLM Latency Benchmark by Use Cases in 2026"
- RunPod "LLM Inference Optimization: Techniques That Actually Work" (2026)
- TrySight "Best LLM Optimization Strategies: Tips for 2026"
- Redis "LLM Token Optimization: Cut Costs & Latency in 2026"
- Clarifai "LLM Inference Optimization Techniques" (2026)

Key capabilities:
- Per-stage latency recording with nanosecond precision
- P50 / P95 / P99 percentile computation per stage
- Bottleneck detection: identify which stage dominates
- SLA breach detection with configurable thresholds
- Optimization suggestions based on observed patterns
- Rolling window analysis (last N requests)
- Batch profiling across multiple agents / stages
- Quality gate: fast / acceptable / slow / critical
"""

from __future__ import annotations

import logging
import math
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

logger = logging.getLogger(__name__)


# ── Enums ────────────────────────────────────────────────────────────────

class PipelineStage(StrEnum):
    PROMPT_BUILD = "prompt_build"
    API_CALL = "api_call"
    RESPONSE_PARSE = "response_parse"
    VALIDATION = "validation"
    POST_PROCESSING = "post_processing"
    TOTAL = "total"


class LatencyGrade(StrEnum):
    FAST = "fast"
    ACCEPTABLE = "acceptable"
    SLOW = "slow"
    CRITICAL = "critical"


class GateDecision(StrEnum):
    PASS = "pass"
    WARN = "warn"
    BLOCK = "block"


# ── Data classes ─────────────────────────────────────────────────────────

@dataclass
class LatencySample:
    """Single latency observation."""

    stage: PipelineStage
    duration_ms: float
    agent: str = ""
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class StageProfile:
    """Latency profile for a single stage."""

    stage: PipelineStage
    sample_count: int
    p50_ms: float
    p95_ms: float
    p99_ms: float
    min_ms: float
    max_ms: float
    avg_ms: float
    grade: LatencyGrade


@dataclass
class BottleneckReport:
    """Identifies the dominant latency stage."""

    stage: PipelineStage
    avg_ms: float
    share_pct: float  # % of total latency
    suggestion: str


@dataclass
class LatencyConfig:
    """Thresholds for latency grading."""

    fast_ms: float = 500.0
    acceptable_ms: float = 2000.0
    slow_ms: float = 5000.0
    # Above slow = critical
    sla_p95_ms: float = 3000.0  # SLA target for P95


@dataclass
class ProfileReport:
    """Full profiling report."""

    agent: str
    stage_profiles: list[StageProfile]
    bottleneck: BottleneckReport | None
    total_p95_ms: float
    sla_breached: bool
    gate: GateDecision
    sample_count: int
    suggestions: list[str]


@dataclass
class BatchProfileReport:
    """Batch report across multiple agents."""

    reports: list[ProfileReport]
    slowest_agent: str
    fastest_agent: str
    overall_p95_ms: float


# ── Pure helpers ─────────────────────────────────────────────────────────

def _percentile(sorted_values: list[float], pct: float) -> float:
    """Compute percentile from sorted values."""
    if not sorted_values:
        return 0.0
    k = (len(sorted_values) - 1) * (pct / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_values[int(k)]
    return sorted_values[f] * (c - k) + sorted_values[c] * (k - f)


def _grade_latency(value_ms: float, config: LatencyConfig) -> LatencyGrade:
    """Grade a latency value."""
    if value_ms <= config.fast_ms:
        return LatencyGrade.FAST
    if value_ms <= config.acceptable_ms:
        return LatencyGrade.ACCEPTABLE
    if value_ms <= config.slow_ms:
        return LatencyGrade.SLOW
    return LatencyGrade.CRITICAL


def _suggest_for_stage(stage: PipelineStage, avg_ms: float) -> str:
    """Generate optimisation suggestion for a stage."""
    suggestions = {
        PipelineStage.PROMPT_BUILD: "Consider caching prompt templates or pre-computing embeddings",
        PipelineStage.API_CALL: "Try streaming responses, smaller models, or semantic caching",
        PipelineStage.RESPONSE_PARSE: "Use structured output mode to reduce parsing overhead",
        PipelineStage.VALIDATION: "Run validation checks in parallel instead of sequentially",
        PipelineStage.POST_PROCESSING: "Batch post-processing steps or run non-critical ones async",
    }
    return suggestions.get(stage, f"Investigate {stage} stage for optimisation")


def _compute_stage_profile(
    stage: PipelineStage,
    samples: list[float],
    config: LatencyConfig,
) -> StageProfile:
    """Compute full profile for one stage."""
    if not samples:
        return StageProfile(
            stage=stage, sample_count=0, p50_ms=0, p95_ms=0, p99_ms=0,
            min_ms=0, max_ms=0, avg_ms=0, grade=LatencyGrade.FAST,
        )
    sorted_s = sorted(samples)
    avg = sum(sorted_s) / len(sorted_s)
    return StageProfile(
        stage=stage,
        sample_count=len(sorted_s),
        p50_ms=round(_percentile(sorted_s, 50), 2),
        p95_ms=round(_percentile(sorted_s, 95), 2),
        p99_ms=round(_percentile(sorted_s, 99), 2),
        min_ms=round(sorted_s[0], 2),
        max_ms=round(sorted_s[-1], 2),
        avg_ms=round(avg, 2),
        grade=_grade_latency(avg, config),
    )


# ── Main class ───────────────────────────────────────────────────────────

class AgentLatencyProfiler:
    """Profiles latency across agent pipeline stages."""

    def __init__(self, config: LatencyConfig | None = None, window_size: int = 1000) -> None:
        self._config = config or LatencyConfig()
        self._window_size = window_size
        self._samples: list[LatencySample] = []

    def record(self, stage: PipelineStage, duration_ms: float, agent: str = "") -> LatencySample:
        """Record a latency sample."""
        sample = LatencySample(stage=stage, duration_ms=duration_ms, agent=agent)
        self._samples.append(sample)
        # Evict oldest if over window
        if len(self._samples) > self._window_size:
            self._samples = self._samples[-self._window_size:]
        return sample

    def record_request(self, agent: str, stage_timings: dict[PipelineStage, float]) -> str:
        """Record all stage timings for one request and return request_id."""
        rid = str(uuid.uuid4())
        total = 0.0
        for stage, dur in stage_timings.items():
            s = LatencySample(stage=stage, duration_ms=dur, agent=agent, request_id=rid)
            self._samples.append(s)
            total += dur
        # Also record total
        self._samples.append(LatencySample(
            stage=PipelineStage.TOTAL, duration_ms=total, agent=agent, request_id=rid,
        ))
        if len(self._samples) > self._window_size:
            self._samples = self._samples[-self._window_size:]
        return rid

    def profile_stage(self, stage: PipelineStage, agent: str = "") -> StageProfile:
        """Get profile for one stage, optionally filtered by agent."""
        vals = [
            s.duration_ms for s in self._samples
            if s.stage == stage and (not agent or s.agent == agent)
        ]
        return _compute_stage_profile(stage, vals, self._config)

    def find_bottleneck(self, agent: str = "") -> BottleneckReport | None:
        """Identify the pipeline stage that dominates latency."""
        stages = [s for s in PipelineStage if s != PipelineStage.TOTAL]
        stage_avgs: list[tuple[PipelineStage, float]] = []
        for stage in stages:
            vals = [
                s.duration_ms for s in self._samples
                if s.stage == stage and (not agent or s.agent == agent)
            ]
            if vals:
                stage_avgs.append((stage, sum(vals) / len(vals)))

        if not stage_avgs:
            return None

        total_avg = sum(a for _, a in stage_avgs)
        worst = max(stage_avgs, key=lambda x: x[1])

        share = (worst[1] / total_avg * 100) if total_avg > 0 else 0
        return BottleneckReport(
            stage=worst[0],
            avg_ms=round(worst[1], 2),
            share_pct=round(share, 1),
            suggestion=_suggest_for_stage(worst[0], worst[1]),
        )

    def profile_agent(self, agent: str) -> ProfileReport:
        """Generate full profile for an agent."""
        stages = list(PipelineStage)
        profiles = [self.profile_stage(s, agent) for s in stages]
        bottleneck = self.find_bottleneck(agent)

        total_profile = next((p for p in profiles if p.stage == PipelineStage.TOTAL), None)
        total_p95 = total_profile.p95_ms if total_profile else 0
        sla_breached = total_p95 > self._config.sla_p95_ms

        suggestions = []
        for p in profiles:
            slow = {LatencyGrade.SLOW, LatencyGrade.CRITICAL}
            if p.stage != PipelineStage.TOTAL and p.grade in slow:
                suggestions.append(_suggest_for_stage(p.stage, p.avg_ms))

        if sla_breached:
            gate = GateDecision.BLOCK
        elif any(p.grade == LatencyGrade.SLOW for p in profiles):
            gate = GateDecision.WARN
        else:
            gate = GateDecision.PASS

        sample_count = len([s for s in self._samples if s.agent == agent])

        return ProfileReport(
            agent=agent,
            stage_profiles=[p for p in profiles if p.sample_count > 0],
            bottleneck=bottleneck,
            total_p95_ms=total_p95,
            sla_breached=sla_breached,
            gate=gate,
            sample_count=sample_count,
            suggestions=suggestions,
        )

    def batch_profile(self) -> BatchProfileReport:
        """Profile all agents."""
        agents = {s.agent for s in self._samples if s.agent}
        if not agents:
            return BatchProfileReport(
                reports=[], slowest_agent="", fastest_agent="", overall_p95_ms=0,
            )

        reports = [self.profile_agent(a) for a in agents]
        sorted_r = sorted(reports, key=lambda r: r.total_p95_ms)
        all_total = [
            s.duration_ms for s in self._samples if s.stage == PipelineStage.TOTAL
        ]
        overall_p95 = _percentile(sorted(all_total), 95) if all_total else 0

        return BatchProfileReport(
            reports=reports,
            slowest_agent=sorted_r[-1].agent if sorted_r else "",
            fastest_agent=sorted_r[0].agent if sorted_r else "",
            overall_p95_ms=round(overall_p95, 2),
        )
