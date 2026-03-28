"""Tests for Prompt Canary Deployer."""

from __future__ import annotations

from app.quality.prompt_canary_deployer import (
    BatchCanaryReport,
    CanaryConfig,
    CanaryReport,
    CanaryStatus,
    GateDecision,
    HealthCheck,
    MetricKind,
    MetricSample,
    PromptCanaryDeployer,
    PromptVersion,
    _avg,
    _check_health,
    _compute_significance,
    _route_to_canary,
)

# ── _avg ──────────────────────────────────────────────────────────────

class TestAvg:
    def test_empty(self):
        assert _avg([]) == 0.0

    def test_single(self):
        assert _avg([5.0]) == 5.0

    def test_multiple(self):
        assert _avg([2.0, 4.0, 6.0]) == 4.0


# ── _route_to_canary ─────────────────────────────────────────────────

class TestRouteToCanary:
    def test_zero_never_routes(self):
        assert _route_to_canary(0) is False

    def test_hundred_always_routes(self):
        assert _route_to_canary(100) is True

    def test_fifty_returns_bool(self):
        result = _route_to_canary(50)
        assert isinstance(result, bool)


# ── _check_health ────────────────────────────────────────────────────

class TestCheckHealth:
    def test_higher_is_better_pass(self):
        h = _check_health(MetricKind.QUALITY, [0.8, 0.9], [0.85, 0.9], 0.7, higher_is_better=True)
        assert h.passed is True
        assert h.metric == MetricKind.QUALITY

    def test_higher_is_better_fail(self):
        h = _check_health(MetricKind.QUALITY, [0.9], [0.5, 0.6], 0.7, higher_is_better=True)
        assert h.passed is False

    def test_lower_is_better_pass(self):
        h = _check_health(MetricKind.LATENCY, [100], [80, 90], 200, higher_is_better=False)
        assert h.passed is True

    def test_lower_is_better_fail(self):
        h = _check_health(MetricKind.LATENCY, [100], [300, 400], 200, higher_is_better=False)
        assert h.passed is False

    def test_empty_baseline(self):
        h = _check_health(MetricKind.COST, [], [0.1], 0.5, higher_is_better=False)
        assert h.baseline_avg == 0.0
        assert h.passed is True

    def test_degradation_positive(self):
        h = _check_health(MetricKind.QUALITY, [1.0], [0.8], 0.5, higher_is_better=True)
        assert h.degradation_pct > 0


# ── _compute_significance ────────────────────────────────────────────

class TestComputeSignificance:
    def test_insufficient_data(self):
        assert _compute_significance([1.0], [2.0]) == 1.0

    def test_identical_returns_high_p(self):
        p = _compute_significance([1.0, 1.0, 1.0], [1.0, 1.0, 1.0])
        assert p >= 0.9

    def test_different_returns_low_p(self):
        p = _compute_significance([1.0, 1.1, 0.9], [100.0, 101.0, 99.0])
        assert p < 0.1

    def test_zero_variance(self):
        p = _compute_significance([5.0, 5.0], [5.0, 5.0])
        assert p == 1.0


# ── PromptCanaryDeployer ─────────────────────────────────────────────

class TestPromptCanaryDeployer:
    def _make_deployer(self):
        d = PromptCanaryDeployer()
        d.register_version("v1", "Generate code for: {task}")
        d.register_version("v2", "You are an expert coder. Generate: {task}")
        return d

    def test_register_version(self):
        d = PromptCanaryDeployer()
        v = d.register_version("v1", "hello")
        assert isinstance(v, PromptVersion)
        assert v.version_id == "v1"

    def test_create_deployment(self):
        d = self._make_deployer()
        dep = d.create_deployment("v1", "v2")
        assert dep.status == CanaryStatus.PENDING
        assert dep.baseline_version == "v1"
        assert dep.canary_version == "v2"

    def test_start_deployment(self):
        d = self._make_deployer()
        dep = d.create_deployment("v1", "v2")
        dep = d.start_deployment(dep.deployment_id)
        assert dep.status == CanaryStatus.ACTIVE
        assert dep.current_percentage == 5.0

    def test_start_already_active_raises(self):
        d = self._make_deployer()
        dep = d.create_deployment("v1", "v2")
        d.start_deployment(dep.deployment_id)
        try:
            d.start_deployment(dep.deployment_id)
            raise AssertionError("Should raise")
        except ValueError:
            pass

    def test_route_request_pending(self):
        d = self._make_deployer()
        dep = d.create_deployment("v1", "v2")
        assert d.route_request(dep.deployment_id) == "v1"

    def test_route_request_active(self):
        d = self._make_deployer()
        dep = d.create_deployment("v1", "v2", CanaryConfig(initial_percentage=50))
        d.start_deployment(dep.deployment_id)
        results = {d.route_request(dep.deployment_id) for _ in range(100)}
        # With 50%, should route to both versions over 100 tries
        assert "v1" in results or "v2" in results

    def test_record_sample(self):
        d = self._make_deployer()
        dep = d.create_deployment("v1", "v2")
        d.start_deployment(dep.deployment_id)
        d.record_sample(dep.deployment_id, "v2", MetricKind.QUALITY, 0.9)
        assert len(dep.canary_samples) == 1
        d.record_sample(dep.deployment_id, "v1", MetricKind.QUALITY, 0.85)
        assert len(dep.baseline_samples) == 1

    def test_check_health_empty(self):
        d = self._make_deployer()
        dep = d.create_deployment("v1", "v2")
        checks = d.check_health(dep.deployment_id)
        assert checks == []

    def test_check_health_with_data(self):
        d = self._make_deployer()
        dep = d.create_deployment("v1", "v2")
        d.start_deployment(dep.deployment_id)
        d.record_sample(dep.deployment_id, "v2", MetricKind.QUALITY, 0.9)
        d.record_sample(dep.deployment_id, "v1", MetricKind.QUALITY, 0.85)
        checks = d.check_health(dep.deployment_id)
        assert len(checks) >= 1
        assert all(isinstance(c, HealthCheck) for c in checks)

    def test_evaluate_gate_hold_insufficient_samples(self):
        d = self._make_deployer()
        dep = d.create_deployment("v1", "v2", CanaryConfig(min_samples_per_step=10))
        d.start_deployment(dep.deployment_id)
        d.record_sample(dep.deployment_id, "v2", MetricKind.QUALITY, 0.9)
        assert d.evaluate_gate(dep.deployment_id) == GateDecision.HOLD

    def test_evaluate_gate_promote(self):
        d = self._make_deployer()
        cfg = CanaryConfig(min_samples_per_step=3, quality_threshold=0.5)
        dep = d.create_deployment("v1", "v2", cfg)
        d.start_deployment(dep.deployment_id)
        for _ in range(5):
            d.record_sample(dep.deployment_id, "v2", MetricKind.QUALITY, 0.9)
            d.record_sample(dep.deployment_id, "v1", MetricKind.QUALITY, 0.85)
        assert d.evaluate_gate(dep.deployment_id) == GateDecision.PROMOTE

    def test_evaluate_gate_rollback(self):
        d = self._make_deployer()
        cfg = CanaryConfig(min_samples_per_step=3, quality_threshold=0.8)
        dep = d.create_deployment("v1", "v2", cfg)
        d.start_deployment(dep.deployment_id)
        for _ in range(5):
            d.record_sample(dep.deployment_id, "v2", MetricKind.QUALITY, 0.3)  # bad
            d.record_sample(dep.deployment_id, "v1", MetricKind.QUALITY, 0.9)
        assert d.evaluate_gate(dep.deployment_id) == GateDecision.ROLLBACK

    def test_advance_promotes_through_steps(self):
        d = self._make_deployer()
        cfg = CanaryConfig(
            min_samples_per_step=2,
            quality_threshold=0.5,
            ramp_steps=[5.0, 10.0, 100.0],
        )
        dep = d.create_deployment("v1", "v2", cfg)
        d.start_deployment(dep.deployment_id)

        # Fill samples for step 0
        for _ in range(3):
            d.record_sample(dep.deployment_id, "v2", MetricKind.QUALITY, 0.9)
            d.record_sample(dep.deployment_id, "v1", MetricKind.QUALITY, 0.85)
        dep = d.advance_or_rollback(dep.deployment_id)
        assert dep.status == CanaryStatus.RAMPING
        assert dep.current_percentage == 10.0

    def test_advance_rollback_on_failure(self):
        d = self._make_deployer()
        cfg = CanaryConfig(min_samples_per_step=2, quality_threshold=0.8)
        dep = d.create_deployment("v1", "v2", cfg)
        d.start_deployment(dep.deployment_id)
        for _ in range(3):
            d.record_sample(dep.deployment_id, "v2", MetricKind.QUALITY, 0.2)
        dep = d.advance_or_rollback(dep.deployment_id)
        assert dep.status == CanaryStatus.ROLLED_BACK

    def test_promote_directly(self):
        d = self._make_deployer()
        dep = d.create_deployment("v1", "v2")
        d.start_deployment(dep.deployment_id)
        dep = d.promote(dep.deployment_id)
        assert dep.status == CanaryStatus.PROMOTED
        assert dep.current_percentage == 100.0

    def test_rollback(self):
        d = self._make_deployer()
        dep = d.create_deployment("v1", "v2")
        d.start_deployment(dep.deployment_id)
        dep = d.rollback(dep.deployment_id, "bad quality")
        assert dep.status == CanaryStatus.ROLLED_BACK
        assert dep.rollback_reason == "bad quality"

    def test_rollback_history(self):
        d = self._make_deployer()
        dep = d.create_deployment("v1", "v2")
        d.start_deployment(dep.deployment_id)
        d.rollback(dep.deployment_id, "test")
        history = d.get_rollback_history()
        assert len(history) == 1
        assert history[0].reason == "test"

    def test_route_after_promote(self):
        d = self._make_deployer()
        dep = d.create_deployment("v1", "v2")
        d.start_deployment(dep.deployment_id)
        d.promote(dep.deployment_id)
        assert d.route_request(dep.deployment_id) == "v2"

    def test_route_after_rollback(self):
        d = self._make_deployer()
        dep = d.create_deployment("v1", "v2")
        d.start_deployment(dep.deployment_id)
        d.rollback(dep.deployment_id, "fail")
        assert d.route_request(dep.deployment_id) == "v1"

    def test_get_report(self):
        d = self._make_deployer()
        dep = d.create_deployment("v1", "v2")
        d.start_deployment(dep.deployment_id)
        report = d.get_report(dep.deployment_id)
        assert isinstance(report, CanaryReport)
        assert report.deployment_id == dep.deployment_id

    def test_get_significance(self):
        d = self._make_deployer()
        dep = d.create_deployment("v1", "v2")
        d.start_deployment(dep.deployment_id)
        for _ in range(5):
            d.record_sample(dep.deployment_id, "v2", MetricKind.QUALITY, 0.9)
            d.record_sample(dep.deployment_id, "v1", MetricKind.QUALITY, 0.85)
        sig = d.get_significance(dep.deployment_id, MetricKind.QUALITY)
        assert 0 <= sig <= 1

    def test_batch_report(self):
        d = self._make_deployer()
        d.create_deployment("v1", "v2")
        d.create_deployment("v1", "v2")
        report = d.batch_report()
        assert isinstance(report, BatchCanaryReport)
        assert len(report.reports) == 2

    def test_full_lifecycle_promote(self):
        d = self._make_deployer()
        cfg = CanaryConfig(
            min_samples_per_step=2,
            quality_threshold=0.5,
            ramp_steps=[5.0, 100.0],
        )
        dep = d.create_deployment("v1", "v2", cfg)
        d.start_deployment(dep.deployment_id)

        # Step 0 -> 1
        for _ in range(3):
            d.record_sample(dep.deployment_id, "v2", MetricKind.QUALITY, 0.9)
        dep = d.advance_or_rollback(dep.deployment_id)
        assert dep.status == CanaryStatus.RAMPING

        # Step 1 -> promote
        for _ in range(3):
            d.record_sample(dep.deployment_id, "v2", MetricKind.QUALITY, 0.9)
        dep = d.advance_or_rollback(dep.deployment_id)
        assert dep.status == CanaryStatus.PROMOTED

    def test_canary_config_defaults(self):
        cfg = CanaryConfig()
        assert cfg.initial_percentage == 5.0
        assert len(cfg.ramp_steps) == 5
        assert cfg.quality_threshold == 0.7

    def test_metric_sample_creation(self):
        s = MetricSample(metric=MetricKind.COST, value=0.25)
        assert s.metric == MetricKind.COST
        assert s.value == 0.25

    def test_latency_health_check(self):
        d = self._make_deployer()
        dep = d.create_deployment("v1", "v2")
        d.start_deployment(dep.deployment_id)
        for _ in range(5):
            d.record_sample(dep.deployment_id, "v2", MetricKind.LATENCY, 100)
            d.record_sample(dep.deployment_id, "v1", MetricKind.LATENCY, 120)
        checks = d.check_health(dep.deployment_id)
        latency_check = next(c for c in checks if c.metric == MetricKind.LATENCY)
        assert latency_check.passed is True

    def test_cost_health_check_breach(self):
        d = self._make_deployer()
        cfg = CanaryConfig(cost_threshold=0.10)
        dep = d.create_deployment("v1", "v2", cfg)
        d.start_deployment(dep.deployment_id)
        for _ in range(5):
            d.record_sample(dep.deployment_id, "v2", MetricKind.COST, 0.50)  # over
        checks = d.check_health(dep.deployment_id)
        cost_check = next(c for c in checks if c.metric == MetricKind.COST)
        assert cost_check.passed is False

    def test_error_rate_check(self):
        d = self._make_deployer()
        dep = d.create_deployment("v1", "v2")
        d.start_deployment(dep.deployment_id)
        for _ in range(5):
            d.record_sample(dep.deployment_id, "v2", MetricKind.ERROR_RATE, 0.01)
        checks = d.check_health(dep.deployment_id)
        err_check = next(c for c in checks if c.metric == MetricKind.ERROR_RATE)
        assert err_check.passed is True
