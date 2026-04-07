"""Aggregate all v1 API routers under a single ``/api/v1`` prefix."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    ai_logs,
    attachments,
    auth,
    comments,
    context,
    dashboard,
    deployments,
    git_ops,
    github_oauth,
    kanban,
    notifications,
    pipeline,
    plans,
    projects,
    reviews,
    test_results,
    ticket_history,
    tickets,
    users,
    webhooks,
)

router = APIRouter(prefix="/api/v1")

# ── Auth ─────────────────────────────────────────────────────────────
router.include_router(auth.router, prefix="/auth", tags=["auth"])
router.include_router(github_oauth.router, prefix="/auth", tags=["auth"])

# ── Users ────────────────────────────────────────────────────────────
router.include_router(users.router, prefix="/users", tags=["users"])

# ── Projects ──────────────────────────────────────────────────────────
router.include_router(projects.router, prefix="/projects", tags=["projects"])

# ── Tickets (CRUD under /projects and /tickets) ─────────────────────
router.include_router(tickets.router, tags=["tickets"])

# ── Kanban (board operations under /tickets and /projects) ───────────
router.include_router(kanban.router, tags=["kanban"])

# ── Ticket History (audit trail) ──────────────────────────────────────
router.include_router(ticket_history.router, tags=["ticket-history"])

# ── Attachments (file uploads on tickets) ─────────────────────────────
router.include_router(attachments.router, tags=["attachments"])

# ── Comments (under /tickets and /comments) ──────────────────────────
router.include_router(comments.router, tags=["comments"])

# ── Plans (AI-generated implementation plans) ────────────────────────
router.include_router(plans.router, tags=["plans"])

# ── Reviews (AI and human code reviews) ──────────────────────────────
router.include_router(reviews.router, tags=["reviews"])

# ── Test Results ─────────────────────────────────────────────────────
router.include_router(test_results.router, tags=["test-results"])

# ── Deployments ──────────────────────────────────────────────────────
router.include_router(deployments.router, tags=["deployments"])

# ── Notifications ────────────────────────────────────────────────────
router.include_router(notifications.router, tags=["notifications"])

# ── Webhooks (n8n + GitHub) ──────────────────────────────────────────
router.include_router(webhooks.router, tags=["webhooks"])

# ── AI Logs ──────────────────────────────────────────────────────────
router.include_router(ai_logs.router, prefix="/ai-logs", tags=["ai-logs"])

# ── Dashboard ────────────────────────────────────────────────────────
router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])

# ── Git Operations ───────────────────────────────────────────────────
router.include_router(git_ops.router, tags=["git"])

# ── Context Engine ───────────────────────────────────────────────────
router.include_router(context.router, tags=["context"])

# ── Pipeline (background task monitoring) ────────────────────────────
router.include_router(pipeline.router, tags=["pipeline"])


@router.get("/ping", tags=["health"])
async def ping() -> dict[str, str]:
    """Lightweight liveness probe scoped to the v1 API."""
    return {"status": "ok", "api": "v1"}
