"""TestResult ORM model — stores results from CI test runs."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.database import Base
from app.models.base_types import DBUUID, generate_uuid, utcnow


class TestResult(Base):
    __test__ = False  # prevent pytest from collecting this ORM model
    __tablename__ = "test_results"

    id: Mapped[uuid.UUID] = mapped_column(
        DBUUID,
        primary_key=True,
        default=generate_uuid,
    )
    ticket_id: Mapped[uuid.UUID] = mapped_column(
        DBUUID,
        ForeignKey("tickets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    run_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        doc="Type of test run: unit, integration, e2e, security, lint.",
    )
    tool_name: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        doc="Tool used for the run, e.g. pytest, playwright, semgrep, ruff.",
    )

    passed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    total_tests: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    passed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    coverage_pct: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        doc="Code coverage percentage (0-100).",
    )
    report_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
        doc="Full structured report from the test tool.",
    )
    log_url: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="URL to the full log output (e.g. GH Actions URL).",
    )
    duration_ms: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=utcnow,
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<TestResult ticket={self.ticket_id} type={self.run_type} "
            f"passed={self.passed} {self.passed_count}/{self.total_tests}>"
        )
