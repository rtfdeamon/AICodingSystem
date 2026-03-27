"""
Event type string constants for WebSocket messages and n8n workflow triggers.

Usage:
    from shared.event_types import WS, N8N

    # In WebSocket handler
    await ws.send_json({"type": WS.TASK_MOVED, "payload": {...}})

    # In n8n webhook trigger check
    if event == N8N.WORKFLOW_TRIGGER_TASK_MOVED:
        ...
"""


class WS:
    """WebSocket event type constants sent between backend and frontend."""

    # Task lifecycle
    TASK_CREATED = "task.created"
    TASK_UPDATED = "task.updated"
    TASK_MOVED = "task.moved"
    TASK_DELETED = "task.deleted"
    TASK_ASSIGNED = "task.assigned"
    TASK_PRIORITY_CHANGED = "task.priority_changed"
    TASK_COMMENT_ADDED = "task.comment_added"

    # Agent activity
    AGENT_STARTED = "agent.started"
    AGENT_PROGRESS = "agent.progress"
    AGENT_COMPLETED = "agent.completed"
    AGENT_FAILED = "agent.failed"
    AGENT_LOG = "agent.log"
    AGENT_TOKENS_USED = "agent.tokens_used"

    # Code review
    REVIEW_REQUESTED = "review.requested"
    REVIEW_APPROVED = "review.approved"
    REVIEW_REJECTED = "review.rejected"
    REVIEW_COMMENT = "review.comment"

    # Pipeline / CI
    PIPELINE_RUN_STARTED = "pipeline.run.started"
    PIPELINE_RUN_COMPLETED = "pipeline.run.completed"
    PIPELINE_RUN_FAILED = "pipeline.run.failed"
    PIPELINE_STEP_STARTED = "pipeline.step.started"
    PIPELINE_STEP_COMPLETED = "pipeline.step.completed"

    # Deploy
    DEPLOY_STARTED = "deploy.started"
    DEPLOY_COMPLETED = "deploy.completed"
    DEPLOY_FAILED = "deploy.failed"
    DEPLOY_ROLLBACK = "deploy.rollback"

    # System
    NOTIFICATION = "notification"
    ERROR = "error"
    HEARTBEAT = "heartbeat"
    CONNECTION_ACK = "connection.ack"
    SUBSCRIBE = "subscribe"
    UNSUBSCRIBE = "unsubscribe"


class N8N:
    """Event type constants used in n8n workflow triggers and webhooks."""

    # Inbound webhooks (GitHub -> n8n)
    GITHUB_PUSH = "n8n.github.push"
    GITHUB_PR_OPENED = "n8n.github.pr.opened"
    GITHUB_PR_MERGED = "n8n.github.pr.merged"
    GITHUB_PR_REVIEW = "n8n.github.pr.review"
    GITHUB_ISSUE_OPENED = "n8n.github.issue.opened"
    GITHUB_ISSUE_COMMENT = "n8n.github.issue.comment"

    # Workflow triggers (backend -> n8n)
    WORKFLOW_TRIGGER_TASK_CREATED = "n8n.trigger.task_created"
    WORKFLOW_TRIGGER_TASK_MOVED = "n8n.trigger.task_moved"
    WORKFLOW_TRIGGER_AGENT_COMPLETED = "n8n.trigger.agent_completed"
    WORKFLOW_TRIGGER_AGENT_FAILED = "n8n.trigger.agent_failed"
    WORKFLOW_TRIGGER_REVIEW_APPROVED = "n8n.trigger.review_approved"
    WORKFLOW_TRIGGER_REVIEW_REJECTED = "n8n.trigger.review_rejected"
    WORKFLOW_TRIGGER_TESTS_PASSED = "n8n.trigger.tests_passed"
    WORKFLOW_TRIGGER_TESTS_FAILED = "n8n.trigger.tests_failed"
    WORKFLOW_TRIGGER_DEPLOY_REQUESTED = "n8n.trigger.deploy_requested"

    # Notification workflows (n8n -> external)
    NOTIFY_SLACK = "n8n.notify.slack"
    NOTIFY_TELEGRAM = "n8n.notify.telegram"
    NOTIFY_EMAIL = "n8n.notify.email"

    # Scheduled workflows
    SCHEDULED_HEALTH_CHECK = "n8n.scheduled.health_check"
    SCHEDULED_STALE_TASK_CHECK = "n8n.scheduled.stale_task_check"
    SCHEDULED_METRICS_REPORT = "n8n.scheduled.metrics_report"


# Flat list of all event type strings for validation
ALL_WS_EVENTS: list[str] = [
    v for k, v in vars(WS).items() if not k.startswith("_")
]

ALL_N8N_EVENTS: list[str] = [
    v for k, v in vars(N8N).items() if not k.startswith("_")
]

ALL_EVENTS: list[str] = ALL_WS_EVENTS + ALL_N8N_EVENTS
