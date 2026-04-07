"""Dashboard schemas — response models for metrics and analytics."""

from __future__ import annotations

from pydantic import BaseModel


class PipelineStats(BaseModel):
    """Pipeline throughput and status metrics."""

    tickets_per_column: dict[str, int] = {}
    avg_time_per_column_hours: dict[str, float] = {}
    total_tickets: int = 0


class AICostMetrics(BaseModel):
    """AI provider cost breakdown."""

    cost_by_agent: dict[str, float] = {}
    cost_by_day: dict[str, float] = {}
    total_cost: float = 0.0
    tokens_total: int = 0


class CodeQualityMetrics(BaseModel):
    """Code quality aggregate metrics."""

    lint_pass_rate: float = 0.0
    test_coverage_avg: float = 0.0
    review_pass_rate: float = 0.0
    security_vuln_count: int = 0


class DeploymentStats(BaseModel):
    """Deployment statistics."""

    deploy_count: int = 0
    rollback_rate: float = 0.0
    avg_deploy_time_ms: int = 0
    success_rate: float = 0.0
