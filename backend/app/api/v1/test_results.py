"""Test result endpoints — view test runs and trigger new ones."""

from __future__ import annotations

import logging
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.test_result import TestResult
from app.models.ticket import Ticket
from app.models.user import User
from app.schemas.test_result import (
    TestGenerateRequest,
    TestGenerateResponse,
    TestResultDetailResponse,
    TestResultResponse,
    TestRunRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# Schemas imported from app.schemas.test_result


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/tickets/{ticket_id}/test-results", response_model=list[TestResultResponse])
async def list_test_results(
    ticket_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: Annotated[User, Depends(get_current_user)],
    run_type: str | None = Query(default=None, description="Filter by run type"),
) -> list[TestResultResponse]:
    """List test results for a ticket."""
    query = (
        select(TestResult)
        .where(TestResult.ticket_id == ticket_id)
        .order_by(TestResult.created_at.desc())
    )
    if run_type:
        query = query.where(TestResult.run_type == run_type)

    result = await db.execute(query)
    results = result.scalars().all()
    return [TestResultResponse.from_orm_result(tr) for tr in results]


@router.get("/test-results/{result_id}", response_model=TestResultDetailResponse)
async def get_test_result(
    result_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: Annotated[User, Depends(get_current_user)],
) -> TestResultDetailResponse:
    """Get a single test result with full report JSON."""
    result = await db.execute(select(TestResult).where(TestResult.id == result_id))
    tr = result.scalar_one_or_none()
    if tr is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Test result not found.")
    return TestResultDetailResponse.from_orm_detail(tr)


@router.post(
    "/tickets/{ticket_id}/tests/run",
    response_model=TestResultResponse,
    status_code=201,
)
async def trigger_test_run(
    ticket_id: uuid.UUID,
    data: TestRunRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> TestResultResponse:
    """Trigger a test run for a ticket."""
    from app.ci.test_runner import run_tests

    # Verify ticket exists
    ticket_result = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
    ticket = ticket_result.scalar_one_or_none()
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found.")

    # Determine project path — use a default if not available
    project_path = "/app"
    if ticket.project:
        project_name = ticket.project.name if hasattr(ticket.project, "name") else "default"
        project_path = f"/app/projects/{project_name}"

    # Run tests
    suite_result = await run_tests(
        project_path=project_path,
        test_type=data.test_type,
        branch=data.branch,
    )

    # Persist result
    test_result = TestResult(
        ticket_id=ticket_id,
        run_type=data.test_type,
        tool_name=suite_result.tool_name,
        passed=suite_result.passed,
        total_tests=suite_result.total,
        passed_count=suite_result.passed_count,
        failed_count=suite_result.failed,
        skipped_count=suite_result.skipped,
        coverage_pct=suite_result.coverage_pct,
        report_json=suite_result.report_json,
        duration_ms=suite_result.duration_ms,
    )
    db.add(test_result)
    await db.flush()
    await db.refresh(test_result)

    logger.info(
        "Test run for ticket %s: type=%s passed=%s total=%d duration=%dms",
        ticket_id,
        data.test_type,
        suite_result.passed,
        suite_result.total,
        suite_result.duration_ms,
    )

    return TestResultResponse.from_orm_result(test_result)


@router.post(
    "/tickets/{ticket_id}/tests/generate",
    response_model=TestGenerateResponse,
    status_code=201,
)
async def generate_tests(
    ticket_id: uuid.UUID,
    data: TestGenerateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> TestGenerateResponse:
    """Trigger AI test generation for a ticket."""
    from app.agents.router import execute_with_fallback, route_task

    # Verify ticket exists
    ticket_result = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
    ticket = ticket_result.scalar_one_or_none()
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found.")

    # Build prompt for test generation
    files_context = "\n".join(data.target_files) if data.target_files else "All relevant files"
    prompt = (
        f"Generate {data.test_type} tests for the following ticket:\n"
        f"Title: {ticket.title}\n"
        f"Description: {ticket.description or 'N/A'}\n"
        f"Acceptance Criteria: {ticket.acceptance_criteria or 'N/A'}\n\n"
        f"Target files:\n{files_context}\n\n"
        f"Generate comprehensive {data.test_type} tests using pytest. "
        f"Include edge cases, error handling, and assertions for all acceptance criteria. "
        f"Output only the test code."
    )

    agent = route_task("test_generation")
    response = await execute_with_fallback(
        agent,
        prompt=prompt,
        db=db,
        ticket_id=ticket_id,
        action_type="test_generation",
    )

    # Count test files/functions in output
    file_count = response.content.count("def test_")

    logger.info(
        "Generated %d test functions for ticket %s (cost=$%.4f)",
        file_count,
        ticket_id,
        response.cost_usd,
    )

    return TestGenerateResponse(
        ticket_id=ticket_id,
        generated_tests=response.content,
        file_count=file_count,
        cost_usd=response.cost_usd,
    )
