"""Test result schemas — request/response models for test results."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from app.models.test_result import TestResult


class TestResultResponse(BaseModel):
    id: uuid.UUID
    ticket_id: uuid.UUID
    run_type: str
    tool_name: str
    passed: bool
    total_tests: int
    passed_count: int
    failed_count: int
    skipped_count: int
    coverage_pct: float | None = None
    log_url: str | None = None
    duration_ms: int
    created_at: str

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_result(cls, tr: TestResult) -> TestResultResponse:
        return cls(
            id=tr.id,
            ticket_id=tr.ticket_id,
            run_type=tr.run_type,
            tool_name=tr.tool_name,
            passed=tr.passed,
            total_tests=tr.total_tests,
            passed_count=tr.passed_count,
            failed_count=tr.failed_count,
            skipped_count=tr.skipped_count,
            coverage_pct=tr.coverage_pct,
            log_url=tr.log_url,
            duration_ms=tr.duration_ms,
            created_at=tr.created_at.isoformat(),
        )


class TestResultDetailResponse(TestResultResponse):
    report_json: dict[str, Any] | None = None

    @classmethod
    def from_orm_detail(cls, tr: TestResult) -> TestResultDetailResponse:
        return cls(
            id=tr.id,
            ticket_id=tr.ticket_id,
            run_type=tr.run_type,
            tool_name=tr.tool_name,
            passed=tr.passed,
            total_tests=tr.total_tests,
            passed_count=tr.passed_count,
            failed_count=tr.failed_count,
            skipped_count=tr.skipped_count,
            coverage_pct=tr.coverage_pct,
            log_url=tr.log_url,
            duration_ms=tr.duration_ms,
            created_at=tr.created_at.isoformat(),
            report_json=tr.report_json,
        )


class TestRunRequest(BaseModel):
    test_type: str = Field(pattern=r"^(unit|integration|e2e|security)$")
    branch: str = "main"


class TestGenerateRequest(BaseModel):
    target_files: list[str] = Field(
        default_factory=list,
        description="List of file paths to generate tests for.",
    )
    test_type: str = Field(default="unit", pattern=r"^(unit|integration|e2e)$")


class TestGenerateResponse(BaseModel):
    ticket_id: uuid.UUID
    generated_tests: str
    file_count: int
    cost_usd: float
