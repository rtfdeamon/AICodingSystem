"""Tests for Agent Latency Profiler."""

from __future__ import annotations

from app.quality.agent_latency_profiler import (
    AgentLatencyProfiler,
    BatchProfileReport,
    BottleneckReport,
    GateDecision,
    LatencyConfig,
    LatencyGrade,
    LatencySample,
    PipelineStage,
    ProfileReport,
    StageProfile,
    _grade_latency,
    _percentile,
    _suggest_for_stage,
)

# ── _percentile ──────────────────────────────────────────────────────

class TestPercentile:
    def test_empty(self):
        assert _percentile([], 50) == 0.0

    def test_single(self):
        assert _percentile([10.0], 50) == 10.0

    def test_median(self):
        assert _percentile([1.0, 2.0, 3.0, 4.0, 5.0], 50) == 3.0

    def test_p95(self):
        vals = sorted(range(1, 101))
        p95 = _percentile([float(v) for v in vals], 95)
        assert 94 <= p95 <= 96

    def test_p99(self):
        vals = sorted(range(1, 101))
        p99 = _percentile([float(v) for v in vals], 99)
        assert 98 <= p99 <= 100


# ── _grade_latency ───────────────────────────────────────────────────

class TestGradeLatency:
    def test_fast(self):
        assert _grade_latency(100, LatencyConfig()) == LatencyGrade.FAST

    def test_acceptable(self):
        assert _grade_latency(1000, LatencyConfig()) == LatencyGrade.ACCEPTABLE

    def test_slow(self):
        assert _grade_latency(3000, LatencyConfig()) == LatencyGrade.SLOW

    def test_critical(self):
        assert _grade_latency(10000, LatencyConfig()) == LatencyGrade.CRITICAL

    def test_boundary_fast(self):
        assert _grade_latency(500, LatencyConfig()) == LatencyGrade.FAST

    def test_boundary_acceptable(self):
        assert _grade_latency(2000, LatencyConfig()) == LatencyGrade.ACCEPTABLE


# ── _suggest_for_stage ───────────────────────────────────────────────

class TestSuggestForStage:
    def test_api_call(self):
        s = _suggest_for_stage(PipelineStage.API_CALL, 5000)
        assert "streaming" in s.lower() or "caching" in s.lower()

    def test_prompt_build(self):
        s = _suggest_for_stage(PipelineStage.PROMPT_BUILD, 1000)
        assert "caching" in s.lower() or "template" in s.lower()

    def test_validation(self):
        s = _suggest_for_stage(PipelineStage.VALIDATION, 500)
        assert "parallel" in s.lower()

    def test_total_fallback(self):
        s = _suggest_for_stage(PipelineStage.TOTAL, 1000)
        assert "total" in s.lower() or "investigate" in s.lower()


# ── AgentLatencyProfiler ────────────────────────────────────────────

class TestAgentLatencyProfiler:
    def test_record_sample(self):
        p = AgentLatencyProfiler()
        s = p.record(PipelineStage.API_CALL, 150.0, "claude")
        assert isinstance(s, LatencySample)
        assert s.duration_ms == 150.0

    def test_record_request(self):
        p = AgentLatencyProfiler()
        rid = p.record_request("claude", {
            PipelineStage.PROMPT_BUILD: 10,
            PipelineStage.API_CALL: 200,
            PipelineStage.RESPONSE_PARSE: 5,
        })
        assert isinstance(rid, str)

    def test_profile_stage(self):
        p = AgentLatencyProfiler()
        for i in range(10):
            p.record(PipelineStage.API_CALL, 100 + i * 10, "claude")
        profile = p.profile_stage(PipelineStage.API_CALL, "claude")
        assert isinstance(profile, StageProfile)
        assert profile.sample_count == 10
        assert profile.p50_ms > 0
        assert profile.p95_ms >= profile.p50_ms

    def test_profile_stage_empty(self):
        p = AgentLatencyProfiler()
        profile = p.profile_stage(PipelineStage.API_CALL)
        assert profile.sample_count == 0
        assert profile.grade == LatencyGrade.FAST

    def test_find_bottleneck(self):
        p = AgentLatencyProfiler()
        p.record(PipelineStage.PROMPT_BUILD, 10, "claude")
        p.record(PipelineStage.API_CALL, 500, "claude")
        p.record(PipelineStage.VALIDATION, 20, "claude")
        bn = p.find_bottleneck("claude")
        assert isinstance(bn, BottleneckReport)
        assert bn.stage == PipelineStage.API_CALL

    def test_find_bottleneck_empty(self):
        p = AgentLatencyProfiler()
        assert p.find_bottleneck() is None

    def test_profile_agent(self):
        p = AgentLatencyProfiler()
        for _ in range(5):
            p.record_request("claude", {
                PipelineStage.PROMPT_BUILD: 10,
                PipelineStage.API_CALL: 200,
                PipelineStage.RESPONSE_PARSE: 5,
                PipelineStage.VALIDATION: 15,
                PipelineStage.POST_PROCESSING: 8,
            })
        report = p.profile_agent("claude")
        assert isinstance(report, ProfileReport)
        assert report.agent == "claude"
        assert report.sample_count > 0
        assert report.gate == GateDecision.PASS

    def test_profile_agent_slow(self):
        p = AgentLatencyProfiler(LatencyConfig(sla_p95_ms=100))
        for _ in range(5):
            p.record_request("claude", {
                PipelineStage.API_CALL: 5000,
            })
        report = p.profile_agent("claude")
        assert report.sla_breached is True
        assert report.gate == GateDecision.BLOCK

    def test_window_eviction(self):
        p = AgentLatencyProfiler(window_size=10)
        for i in range(20):
            p.record(PipelineStage.API_CALL, float(i), "claude")
        # Should only keep last 10
        profile = p.profile_stage(PipelineStage.API_CALL)
        assert profile.sample_count == 10
        assert profile.min_ms >= 10.0

    def test_batch_profile(self):
        p = AgentLatencyProfiler()
        for _ in range(5):
            p.record_request("claude", {PipelineStage.API_CALL: 200})
            p.record_request("gpt4", {PipelineStage.API_CALL: 300})
        report = p.batch_profile()
        assert isinstance(report, BatchProfileReport)
        assert len(report.reports) == 2
        assert report.fastest_agent in {"claude", "gpt4"}
        assert report.slowest_agent in {"claude", "gpt4"}

    def test_batch_profile_empty(self):
        p = AgentLatencyProfiler()
        report = p.batch_profile()
        assert report.fastest_agent == ""
        assert report.slowest_agent == ""

    def test_multiple_stages_profiled(self):
        p = AgentLatencyProfiler()
        p.record_request("claude", {
            PipelineStage.PROMPT_BUILD: 10,
            PipelineStage.API_CALL: 200,
        })
        report = p.profile_agent("claude")
        stage_names = {sp.stage for sp in report.stage_profiles}
        assert PipelineStage.PROMPT_BUILD in stage_names
        assert PipelineStage.API_CALL in stage_names
        assert PipelineStage.TOTAL in stage_names

    def test_bottleneck_share_pct(self):
        p = AgentLatencyProfiler()
        p.record(PipelineStage.PROMPT_BUILD, 10, "a")
        p.record(PipelineStage.API_CALL, 90, "a")
        bn = p.find_bottleneck("a")
        assert bn is not None
        assert bn.share_pct == 90.0

    def test_suggestions_for_slow_stages(self):
        p = AgentLatencyProfiler(LatencyConfig(slow_ms=100))
        for _ in range(5):
            p.record_request("claude", {
                PipelineStage.API_CALL: 5000,
                PipelineStage.VALIDATION: 200,
            })
        report = p.profile_agent("claude")
        assert len(report.suggestions) > 0

    def test_latency_config_defaults(self):
        cfg = LatencyConfig()
        assert cfg.fast_ms == 500.0
        assert cfg.sla_p95_ms == 3000.0

    def test_record_returns_sample(self):
        p = AgentLatencyProfiler()
        s = p.record(PipelineStage.TOTAL, 100, "x")
        assert s.stage == PipelineStage.TOTAL
        assert s.agent == "x"

    def test_grade_boundary_slow(self):
        assert _grade_latency(5000, LatencyConfig()) == LatencyGrade.SLOW

    def test_filter_by_agent(self):
        p = AgentLatencyProfiler()
        p.record(PipelineStage.API_CALL, 100, "claude")
        p.record(PipelineStage.API_CALL, 500, "gpt4")
        prof_claude = p.profile_stage(PipelineStage.API_CALL, "claude")
        assert prof_claude.sample_count == 1
        assert prof_claude.avg_ms == 100.0

    def test_overall_p95(self):
        p = AgentLatencyProfiler()
        for _ in range(20):
            p.record_request("claude", {PipelineStage.API_CALL: 100})
        report = p.batch_profile()
        assert report.overall_p95_ms > 0
