"""Tests for Agent SLA Monitor."""

from __future__ import annotations

from app.quality.agent_sla_monitor import (
    AgentSLAMonitor,
    AgentSLAReport,
    BatchSLAReport,
    BreachSeverity,
    ComplianceStatus,
    GateDecision,
    MetricObservation,
    SLAContract,
    SLAMetric,
    SLATarget,
    _check_compliance,
    _classify_severity,
    _compliance_status,
    _compute_error_budget,
)

# ── _classify_severity ───────────────────────────────────────────────

class TestClassifySeverity:
    def test_minor(self):
        assert _classify_severity(10) == BreachSeverity.MINOR

    def test_major(self):
        assert _classify_severity(30) == BreachSeverity.MAJOR

    def test_critical(self):
        assert _classify_severity(60) == BreachSeverity.CRITICAL

    def test_boundary_minor(self):
        assert _classify_severity(19) == BreachSeverity.MINOR

    def test_boundary_major(self):
        assert _classify_severity(20) == BreachSeverity.MAJOR


# ── _check_compliance ────────────────────────────────────────────────

class TestCheckCompliance:
    def test_empty(self):
        pct, breaches = _check_compliance([], 0.5, higher_is_better=False)
        assert pct == 100.0
        assert breaches == 0

    def test_all_compliant_lower(self):
        pct, breaches = _check_compliance([0.1, 0.2, 0.3], 0.5, higher_is_better=False)
        assert pct == 100.0
        assert breaches == 0

    def test_all_breached_lower(self):
        pct, breaches = _check_compliance([0.6, 0.7, 0.8], 0.5, higher_is_better=False)
        assert pct == 0.0
        assert breaches == 3

    def test_all_compliant_higher(self):
        pct, breaches = _check_compliance([0.8, 0.9, 1.0], 0.7, higher_is_better=True)
        assert pct == 100.0

    def test_partial_breach(self):
        pct, breaches = _check_compliance([0.1, 0.6, 0.3], 0.5, higher_is_better=False)
        assert breaches == 1
        assert 60 < pct < 70


# ── _compliance_status ───────────────────────────────────────────────

class TestComplianceStatus:
    def test_compliant(self):
        assert _compliance_status(99.5, 80.0) == ComplianceStatus.COMPLIANT

    def test_at_risk(self):
        assert _compliance_status(85.0, 80.0) == ComplianceStatus.AT_RISK

    def test_breached(self):
        assert _compliance_status(50.0, 80.0) == ComplianceStatus.BREACHED


# ── _compute_error_budget ────────────────────────────────────────────

class TestComputeErrorBudget:
    def test_no_observations(self):
        assert _compute_error_budget(0, 0, 0.5) == 100.0

    def test_full_budget(self):
        assert _compute_error_budget(1000, 0, 0.5) == 100.0

    def test_half_budget(self):
        result = _compute_error_budget(1000, 3, 0.5)
        assert 30 < result < 50

    def test_exhausted(self):
        result = _compute_error_budget(1000, 10, 0.5)
        assert result == 0.0


# ── AgentSLAMonitor ──────────────────────────────────────────────────

class TestAgentSLAMonitor:
    def _make_monitor(self):
        m = AgentSLAMonitor()
        m.create_default_contract("claude")
        return m

    def test_register_contract(self):
        m = AgentSLAMonitor()
        contract = SLAContract(
            agent="claude",
            targets=[SLATarget(metric=SLAMetric.LATENCY_P95, target_value=3000)],
        )
        m.register_contract(contract)
        report = m.evaluate_agent("claude")
        assert report.agent == "claude"

    def test_create_default_contract(self):
        m = AgentSLAMonitor()
        contract = m.create_default_contract("claude")
        assert contract.agent == "claude"
        assert len(contract.targets) == 5

    def test_observe_compliant(self):
        m = self._make_monitor()
        obs = m.observe("claude", SLAMetric.LATENCY_P95, 1000)
        assert isinstance(obs, MetricObservation)

    def test_observe_breach(self):
        m = self._make_monitor()
        m.observe("claude", SLAMetric.LATENCY_P95, 5000)  # over 3000 target
        breaches = m.get_breaches("claude")
        assert len(breaches) == 1
        valid = {BreachSeverity.MINOR, BreachSeverity.MAJOR, BreachSeverity.CRITICAL}
        assert breaches[0].severity in valid

    def test_observe_batch(self):
        m = self._make_monitor()
        results = m.observe_batch("claude", {
            SLAMetric.LATENCY_P95: 1000,
            SLAMetric.QUALITY_FLOOR: 0.9,
        })
        assert len(results) == 2

    def test_evaluate_agent_compliant(self):
        m = self._make_monitor()
        for _ in range(10):
            m.observe("claude", SLAMetric.LATENCY_P95, 1000)
            m.observe("claude", SLAMetric.QUALITY_FLOOR, 0.9)
            m.observe("claude", SLAMetric.COST_CEILING, 0.10)
            m.observe("claude", SLAMetric.ERROR_RATE, 0.01)
            m.observe("claude", SLAMetric.AVAILABILITY, 1.0)
        report = m.evaluate_agent("claude")
        assert isinstance(report, AgentSLAReport)
        assert report.overall_status == ComplianceStatus.COMPLIANT
        assert report.gate == GateDecision.PASS

    def test_evaluate_agent_breached(self):
        m = self._make_monitor()
        for _ in range(10):
            m.observe("claude", SLAMetric.LATENCY_P95, 10000)  # way over
        report = m.evaluate_agent("claude")
        assert report.overall_status == ComplianceStatus.BREACHED
        assert report.gate == GateDecision.BLOCK

    def test_evaluate_no_contract(self):
        m = AgentSLAMonitor()
        report = m.evaluate_agent("unknown")
        assert report.overall_status == ComplianceStatus.COMPLIANT

    def test_get_breaches_filtered(self):
        m = self._make_monitor()
        m.create_default_contract("gpt4")
        m.observe("claude", SLAMetric.LATENCY_P95, 5000)
        m.observe("gpt4", SLAMetric.LATENCY_P95, 5000)
        claude_breaches = m.get_breaches("claude")
        all_breaches = m.get_breaches()
        assert len(claude_breaches) == 1
        assert len(all_breaches) == 2

    def test_batch_evaluate(self):
        m = self._make_monitor()
        m.create_default_contract("gpt4")
        for _ in range(5):
            m.observe("claude", SLAMetric.LATENCY_P95, 1000)
            m.observe("gpt4", SLAMetric.LATENCY_P95, 5000)
        report = m.batch_evaluate()
        assert isinstance(report, BatchSLAReport)
        assert len(report.reports) == 2

    def test_error_budget_tracking(self):
        m = self._make_monitor()
        for _ in range(100):
            m.observe("claude", SLAMetric.LATENCY_P95, 1000)
        report = m.evaluate_agent("claude")
        assert report.error_budget_remaining_pct == 100.0

    def test_error_budget_consumed(self):
        m = self._make_monitor()
        # Mix of good and bad
        for _ in range(90):
            m.observe("claude", SLAMetric.LATENCY_P95, 1000)
        for _ in range(10):
            m.observe("claude", SLAMetric.LATENCY_P95, 5000)
        report = m.evaluate_agent("claude")
        assert report.error_budget_remaining_pct < 100.0

    def test_quality_floor_higher_is_better(self):
        m = self._make_monitor()
        m.observe("claude", SLAMetric.QUALITY_FLOOR, 0.3)  # below 0.7
        breaches = m.get_breaches("claude")
        assert len(breaches) == 1

    def test_availability_breach(self):
        m = self._make_monitor()
        m.observe("claude", SLAMetric.AVAILABILITY, 0.5)  # below 0.99
        breaches = m.get_breaches("claude")
        assert any(b.metric == SLAMetric.AVAILABILITY for b in breaches)

    def test_severity_minor(self):
        m = self._make_monitor()
        # 3500 vs target 3000 = ~17% deviation = minor
        m.observe("claude", SLAMetric.LATENCY_P95, 3500)
        breaches = m.get_breaches("claude")
        assert breaches[0].severity == BreachSeverity.MINOR

    def test_severity_critical(self):
        m = self._make_monitor()
        # 10000 vs target 3000 = ~233% deviation = critical
        m.observe("claude", SLAMetric.LATENCY_P95, 10000)
        breaches = m.get_breaches("claude")
        assert breaches[0].severity == BreachSeverity.CRITICAL

    def test_metric_compliance_details(self):
        m = self._make_monitor()
        for _ in range(10):
            m.observe("claude", SLAMetric.LATENCY_P95, 1000)
        report = m.evaluate_agent("claude")
        latency_mc = next(
            mc for mc in report.metric_compliance
            if mc.metric == SLAMetric.LATENCY_P95
        )
        assert latency_mc.compliance_pct == 100.0
        assert latency_mc.status == ComplianceStatus.COMPLIANT

    def test_observation_count(self):
        m = self._make_monitor()
        for _ in range(5):
            m.observe("claude", SLAMetric.LATENCY_P95, 1000)
        report = m.evaluate_agent("claude")
        assert report.observation_count == 5

    def test_batch_counts(self):
        m = AgentSLAMonitor()
        m.create_default_contract("a")
        m.create_default_contract("b")
        for _ in range(5):
            m.observe("a", SLAMetric.LATENCY_P95, 1000)
            m.observe("b", SLAMetric.LATENCY_P95, 10000)
        report = m.batch_evaluate()
        assert report.compliant_count + report.at_risk_count + report.breached_count == 2
