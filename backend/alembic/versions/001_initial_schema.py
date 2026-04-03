"""Initial schema — all tables, enums, indexes for the AI Coding Pipeline.

Revision ID: 001_initial
Revises: None
Create Date: 2026-03-26

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Extensions ────────────────────────────────────────────────────
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "vector"')

    # ── Enums ─────────────────────────────────────────────────────────
    priority_enum = postgresql.ENUM(
        "P0",
        "P1",
        "P2",
        "P3",
        name="priority_enum",
        create_type=True,
    )

    column_name_enum = postgresql.ENUM(
        "backlog",
        "ai_planning",
        "plan_review",
        "ai_coding",
        "code_review",
        "staging",
        "staging_verification",
        "production",
        name="column_name_enum",
        create_type=True,
    )

    plan_status_enum = postgresql.ENUM(
        "pending",
        "approved",
        "rejected",
        "superseded",
        name="plan_status_enum",
        create_type=True,
    )

    ai_log_status_enum = postgresql.ENUM(
        "success",
        "error",
        "timeout",
        "fallback",
        name="ai_log_status_enum",
        create_type=True,
    )

    code_gen_status_enum = postgresql.ENUM(
        "in_progress",
        "completed",
        "failed",
        "retry",
        name="code_gen_status_enum",
        create_type=True,
    )

    reviewer_type_enum = postgresql.ENUM(
        "user",
        "ai_agent",
        name="reviewer_type_enum",
        create_type=True,
    )

    review_decision_enum = postgresql.ENUM(
        "approved",
        "rejected",
        "changes_requested",
        name="review_decision_enum",
        create_type=True,
    )

    deploy_environment_enum = postgresql.ENUM(
        "staging",
        "production",
        name="deploy_environment_enum",
        create_type=True,
    )

    deploy_type_enum = postgresql.ENUM(
        "full",
        "canary",
        name="deploy_type_enum",
        create_type=True,
    )

    deploy_status_enum = postgresql.ENUM(
        "pending",
        "deploying",
        "deployed",
        "rolled_back",
        "failed",
        name="deploy_status_enum",
        create_type=True,
    )

    notification_channel_enum = postgresql.ENUM(
        "in_app",
        "slack",
        "telegram",
        name="notification_channel_enum",
        create_type=True,
    )

    # ── users ─────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("email", sa.String(320), nullable=False, unique=True),
        sa.Column("hashed_password", sa.Text, nullable=True),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("role", sa.String(20), nullable=False, server_default="owner"),
        sa.Column("avatar_url", sa.String(2048), nullable=True),
        sa.Column("is_active", sa.Boolean, server_default="true", nullable=False),
        sa.Column("github_id", sa.String(64), nullable=True, unique=True),
        sa.Column("oauth_provider", sa.String(32), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_users_email", "users", ["email"])
    op.create_index("ix_users_github_id", "users", ["github_id"])

    # ── projects ──────────────────────────────────────────────────────
    op.create_table(
        "projects",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(255), nullable=False, unique=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("github_repo_url", sa.String(2048), nullable=True),
        sa.Column("github_repo_id", sa.String(64), nullable=True),
        sa.Column("default_branch", sa.String(128), server_default="main", nullable=False),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_projects_slug", "projects", ["slug"])

    # ── tickets ───────────────────────────────────────────────────────
    op.create_table(
        "tickets",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ticket_number", sa.Integer, nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("acceptance_criteria", sa.Text, nullable=True),
        sa.Column(
            "priority",
            priority_enum,
            server_default="P2",
            nullable=False,
        ),
        sa.Column(
            "column_name",
            column_name_enum,
            server_default="backlog",
            nullable=False,
        ),
        sa.Column(
            "assignee_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "reporter_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("story_points", sa.Integer, nullable=True),
        sa.Column("labels", postgresql.ARRAY(sa.String(64)), server_default="{}", nullable=True),
        sa.Column("branch_name", sa.String(255), nullable=True),
        sa.Column("pr_url", sa.String(2048), nullable=True),
        sa.Column("retry_count", sa.Integer, server_default="0", nullable=False),
        sa.Column("position", sa.Integer, server_default="0", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_tickets_project_id", "tickets", ["project_id"])
    op.create_index("ix_tickets_column_name", "tickets", ["column_name"])
    op.create_index("ix_tickets_project_column", "tickets", ["project_id", "column_name"])

    # ── ticket_history ────────────────────────────────────────────────
    op.create_table(
        "ticket_history",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "ticket_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tickets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "actor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("actor_type", sa.String(20), server_default="user", nullable=False),
        sa.Column("from_column", sa.String(40), nullable=True),
        sa.Column("to_column", sa.String(40), nullable=True),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("details", postgresql.JSONB, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_ticket_history_ticket_id", "ticket_history", ["ticket_id"])

    # ── comments ──────────────────────────────────────────────────────
    op.create_table(
        "comments",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "ticket_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tickets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "author_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("author_type", sa.String(20), server_default="user", nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column(
            "parent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("comments.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_comments_ticket_id", "comments", ["ticket_id"])
    op.create_index("ix_comments_parent_id", "comments", ["parent_id"])

    # ── ai_logs ───────────────────────────────────────────────────────
    op.create_table(
        "ai_logs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "ticket_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tickets.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("agent_name", sa.String(64), nullable=False),
        sa.Column("action_type", sa.String(64), nullable=False),
        sa.Column("model_id", sa.String(128), nullable=False),
        sa.Column("prompt_text", sa.Text, nullable=True),
        sa.Column("response_text", sa.Text, nullable=True),
        sa.Column("prompt_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Float, nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.Integer, nullable=False, server_default="0"),
        sa.Column("status", ai_log_status_enum, nullable=False, server_default="success"),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("metadata", postgresql.JSONB, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_ai_logs_ticket_id", "ai_logs", ["ticket_id"])
    op.create_index("ix_ai_logs_agent_name", "ai_logs", ["agent_name"])
    op.create_index("ix_ai_logs_action_type", "ai_logs", ["action_type"])

    # ── ai_plans ──────────────────────────────────────────────────────
    op.create_table(
        "ai_plans",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "ticket_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tickets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("agent_name", sa.String(64), nullable=False),
        sa.Column("plan_markdown", sa.Text, nullable=False),
        sa.Column("subtasks", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("file_list", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("status", plan_status_enum, nullable=False, server_default="pending"),
        sa.Column("review_comment", sa.Text, nullable=True),
        sa.Column(
            "reviewed_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("prompt_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Float, nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_ai_plans_ticket_id", "ai_plans", ["ticket_id"])

    # ── ai_code_generations ───────────────────────────────────────────
    op.create_table(
        "ai_code_generations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "ticket_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tickets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "plan_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ai_plans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("subtask_index", sa.Integer, nullable=False),
        sa.Column("agent_name", sa.String(64), nullable=False),
        sa.Column("branch_name", sa.String(255), nullable=False),
        sa.Column("files_changed", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("commit_sha", sa.String(64), nullable=True),
        sa.Column("status", code_gen_status_enum, nullable=False, server_default="in_progress"),
        sa.Column("retry_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("lint_passed", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("test_passed", sa.Boolean, nullable=False, server_default="false"),
        sa.Column(
            "log_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ai_logs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_ai_code_generations_ticket_id", "ai_code_generations", ["ticket_id"])
    op.create_index("ix_ai_code_generations_plan_id", "ai_code_generations", ["plan_id"])

    # ── reviews ───────────────────────────────────────────────────────
    op.create_table(
        "reviews",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "ticket_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tickets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "reviewer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("reviewer_type", reviewer_type_enum, nullable=False),
        sa.Column("agent_name", sa.String(64), nullable=True),
        sa.Column("decision", review_decision_enum, nullable=False),
        sa.Column("body", sa.Text, nullable=True),
        sa.Column("inline_comments", postgresql.JSONB, nullable=True),
        sa.Column(
            "log_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ai_logs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_reviews_ticket_id", "reviews", ["ticket_id"])

    # ── test_results ──────────────────────────────────────────────────
    op.create_table(
        "test_results",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "ticket_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tickets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("run_type", sa.String(32), nullable=False),
        sa.Column("tool_name", sa.String(64), nullable=False),
        sa.Column("passed", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("total_tests", sa.Integer, nullable=False, server_default="0"),
        sa.Column("passed_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("skipped_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("coverage_pct", sa.Float, nullable=True),
        sa.Column("report_json", postgresql.JSONB, nullable=True),
        sa.Column("log_url", sa.Text, nullable=True),
        sa.Column("duration_ms", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_test_results_ticket_id", "test_results", ["ticket_id"])

    # ── deployments ───────────────────────────────────────────────────
    op.create_table(
        "deployments",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "ticket_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tickets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("environment", deploy_environment_enum, nullable=False),
        sa.Column("deploy_type", deploy_type_enum, nullable=False, server_default="full"),
        sa.Column("canary_pct", sa.Integer, nullable=True),
        sa.Column("status", deploy_status_enum, nullable=False, server_default="pending"),
        sa.Column(
            "initiated_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("commit_sha", sa.String(64), nullable=True),
        sa.Column("build_url", sa.Text, nullable=True),
        sa.Column("health_check", postgresql.JSONB, nullable=True),
        sa.Column("rollback_reason", sa.Text, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_deployments_ticket_id", "deployments", ["ticket_id"])

    # ── code_embeddings ───────────────────────────────────────────────
    op.create_table(
        "code_embeddings",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("file_path", sa.String(2048), nullable=False),
        sa.Column("chunk_index", sa.Integer, nullable=False, server_default="0"),
        sa.Column("chunk_text", sa.Text, nullable=False),
        sa.Column("language", sa.String(64), nullable=False, server_default="unknown"),
        sa.Column("symbol_name", sa.String(512), nullable=True),
        sa.Column("commit_sha", sa.String(40), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    # Add the vector column via raw SQL (pgvector)
    op.execute("ALTER TABLE code_embeddings ADD COLUMN embedding vector(1536) NOT NULL")

    op.create_index("ix_code_embeddings_project_id", "code_embeddings", ["project_id"])
    op.create_index(
        "ix_code_embeddings_project_file",
        "code_embeddings",
        ["project_id", "file_path"],
    )
    # IVFFlat index for cosine similarity search
    op.execute(
        "CREATE INDEX ix_code_embeddings_embedding "
        "ON code_embeddings USING ivfflat (embedding vector_cosine_ops) "
        "WITH (lists = 100)"
    )

    # ── notifications ─────────────────────────────────────────────────
    op.create_table(
        "notifications",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "ticket_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tickets.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("channel", notification_channel_enum, nullable=False, server_default="in_app"),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("is_read", sa.Boolean, nullable=False, server_default="false"),
        sa.Column(
            "sent_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
    op.create_index("ix_notifications_ticket_id", "notifications", ["ticket_id"])


def downgrade() -> None:
    # ── Drop tables (reverse dependency order) ────────────────────────
    op.drop_table("notifications")
    op.drop_index("ix_code_embeddings_embedding", table_name="code_embeddings")
    op.drop_table("code_embeddings")
    op.drop_table("deployments")
    op.drop_table("test_results")
    op.drop_table("reviews")
    op.drop_table("ai_code_generations")
    op.drop_table("ai_plans")
    op.drop_table("ai_logs")
    op.drop_table("comments")
    op.drop_table("ticket_history")
    op.drop_table("tickets")
    op.drop_table("projects")
    op.drop_table("users")

    # ── Drop enums ────────────────────────────────────────────────────
    op.execute("DROP TYPE IF EXISTS notification_channel_enum")
    op.execute("DROP TYPE IF EXISTS deploy_status_enum")
    op.execute("DROP TYPE IF EXISTS deploy_type_enum")
    op.execute("DROP TYPE IF EXISTS deploy_environment_enum")
    op.execute("DROP TYPE IF EXISTS review_decision_enum")
    op.execute("DROP TYPE IF EXISTS reviewer_type_enum")
    op.execute("DROP TYPE IF EXISTS code_gen_status_enum")
    op.execute("DROP TYPE IF EXISTS ai_log_status_enum")
    op.execute("DROP TYPE IF EXISTS plan_status_enum")
    op.execute("DROP TYPE IF EXISTS column_name_enum")
    op.execute("DROP TYPE IF EXISTS priority_enum")

    # ── Drop extensions ───────────────────────────────────────────────
    op.execute('DROP EXTENSION IF EXISTS "vector"')
    op.execute('DROP EXTENSION IF EXISTS "pgcrypto"')
