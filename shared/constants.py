"""
Shared constants for the AI-Driven Coding Pipeline.
Used by backend, agents, and n8n workflows.

Canonical source of truth for columns, roles, and event types.
Backend models (app/models/ticket.py) and frontend types MUST stay in sync
with these definitions.
"""

from enum import StrEnum


# ---------------------------------------------------------------------------
# Kanban columns (ordered left-to-right) — matches backend ColumnName
# ---------------------------------------------------------------------------

class KanbanColumn(StrEnum):
    BACKLOG = "backlog"
    AI_PLANNING = "ai_planning"
    PLAN_REVIEW = "plan_review"
    AI_CODING = "ai_coding"
    CODE_REVIEW = "code_review"
    STAGING = "staging"
    STAGING_VERIFICATION = "staging_verification"
    PRODUCTION = "production"


KANBAN_COLUMNS: list[str] = [col.value for col in KanbanColumn]


# ---------------------------------------------------------------------------
# Roles — matches backend User.role and frontend UserRole
# ---------------------------------------------------------------------------

class Role(StrEnum):
    OWNER = "owner"
    PM_LEAD = "pm_lead"
    DEVELOPER = "developer"
    AI_AGENT = "ai_agent"


ROLES: list[str] = [role.value for role in Role]


# ---------------------------------------------------------------------------
# Human gate columns — transitions OUT of these require human approval
# ---------------------------------------------------------------------------

HUMAN_GATE_COLUMNS: list[str] = [
    KanbanColumn.PLAN_REVIEW,
    KanbanColumn.CODE_REVIEW,
    KanbanColumn.STAGING_VERIFICATION,
]


# ---------------------------------------------------------------------------
# Transition rules
# Keys are (from_column, to_column) pairs.
# Values describe which roles may perform the transition.
# Production gate: pm_lead ONLY (per TZ requirement).
# ---------------------------------------------------------------------------

TRANSITION_RULES: dict[tuple[str, str], dict] = {
    # backlog -> ai_planning: PM or owner queues ticket
    (KanbanColumn.BACKLOG, KanbanColumn.AI_PLANNING): {
        "roles": [Role.PM_LEAD, Role.OWNER],
    },
    # ai_planning -> plan_review: AI completes planning
    (KanbanColumn.AI_PLANNING, KanbanColumn.PLAN_REVIEW): {
        "roles": [Role.AI_AGENT, Role.PM_LEAD, Role.OWNER],
    },
    # plan_review -> ai_coding: PM approves plan
    (KanbanColumn.PLAN_REVIEW, KanbanColumn.AI_CODING): {
        "roles": [Role.PM_LEAD, Role.OWNER],
    },
    # plan_review -> backlog: PM rejects plan
    (KanbanColumn.PLAN_REVIEW, KanbanColumn.BACKLOG): {
        "roles": [Role.PM_LEAD, Role.OWNER],
    },
    # ai_coding -> code_review: AI completes coding
    (KanbanColumn.AI_CODING, KanbanColumn.CODE_REVIEW): {
        "roles": [Role.AI_AGENT, Role.PM_LEAD, Role.OWNER],
    },
    # code_review -> staging: reviewer approves code
    (KanbanColumn.CODE_REVIEW, KanbanColumn.STAGING): {
        "roles": [Role.DEVELOPER, Role.PM_LEAD, Role.OWNER],
    },
    # code_review -> ai_coding: reviewer requests changes
    (KanbanColumn.CODE_REVIEW, KanbanColumn.AI_CODING): {
        "roles": [Role.DEVELOPER, Role.PM_LEAD, Role.OWNER],
    },
    # staging -> staging_verification: deploy to staging complete
    (KanbanColumn.STAGING, KanbanColumn.STAGING_VERIFICATION): {
        "roles": [Role.AI_AGENT, Role.DEVELOPER, Role.PM_LEAD, Role.OWNER],
    },
    # staging_verification -> production: PM ONLY (production gate)
    (KanbanColumn.STAGING_VERIFICATION, KanbanColumn.PRODUCTION): {
        "roles": [Role.PM_LEAD],
    },
    # staging_verification -> ai_coding: verification failed, rework
    (KanbanColumn.STAGING_VERIFICATION, KanbanColumn.AI_CODING): {
        "roles": [Role.DEVELOPER, Role.PM_LEAD, Role.OWNER],
    },
}


# ---------------------------------------------------------------------------
# Agent routing table
# ---------------------------------------------------------------------------

AGENT_ROUTING_TABLE: dict[str, str] = {
    KanbanColumn.AI_PLANNING: "planner-agent",
    KanbanColumn.AI_CODING: "coder-agent",
    KanbanColumn.STAGING: "deploy-agent",
}


# ---------------------------------------------------------------------------
# Fallback chain — if the primary AI provider fails, try the next
# ---------------------------------------------------------------------------

FALLBACK_CHAIN: list[str] = [
    "anthropic-claude",
    "openai-gpt",
    "google-gemini",
]


# ---------------------------------------------------------------------------
# WebSocket / SSE event types — canonical event names for real-time updates.
# Frontend and backend MUST use these exact strings.
# ---------------------------------------------------------------------------

class EventType(StrEnum):
    # Ticket events
    TICKET_CREATED = "ticket.created"
    TICKET_UPDATED = "ticket.updated"
    TICKET_MOVED = "ticket.moved"
    TICKET_DELETED = "ticket.deleted"

    # Comment events
    COMMENT_ADDED = "comment.added"

    # Agent events
    AGENT_STARTED = "agent.started"
    AGENT_PROGRESS = "agent.progress"
    AGENT_COMPLETED = "agent.completed"
    AGENT_FAILED = "agent.failed"

    # Review / gate events
    REVIEW_REQUESTED = "review.requested"
    REVIEW_APPROVED = "review.approved"
    REVIEW_REJECTED = "review.rejected"

    # Pipeline events
    PIPELINE_STARTED = "pipeline.started"
    PIPELINE_COMPLETED = "pipeline.completed"
    PIPELINE_FAILED = "pipeline.failed"

    # Deploy events
    DEPLOY_STARTED = "deploy.started"
    DEPLOY_COMPLETED = "deploy.completed"
    DEPLOY_FAILED = "deploy.failed"

    # System events
    NOTIFICATION = "notification"
    ERROR = "error"
    HEARTBEAT = "heartbeat"


EVENT_TYPES: list[str] = [evt.value for evt in EventType]
