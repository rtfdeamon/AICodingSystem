"""Formal ticket state machine with side-effect triggers for the AI pipeline."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ticket import ColumnName, Ticket
from app.models.ticket_history import TicketHistory
from app.services.kanban_service import TRANSITION_RULES, TransitionRule

logger = logging.getLogger(__name__)


class TicketStateMachine:
    """Manages ticket state transitions and triggers pipeline side effects.

    Wraps the raw transition rules from :mod:`kanban_service` with richer
    validation and automatic side-effect dispatch (AI planning, coding,
    CI/CD, deployment).
    """

    # ── Validation ───────────────────────────────────────────────────

    @staticmethod
    def can_transition(
        ticket: Ticket,
        to_column: str,
        actor_role: str,
    ) -> tuple[bool, str]:
        """Check whether *ticket* may transition to *to_column*.

        Returns ``(True, "")`` on success or ``(False, reason)`` on failure.
        """
        from_column = (
            ticket.column_name.value
            if isinstance(ticket.column_name, ColumnName)
            else ticket.column_name
        )
        key = (from_column, to_column)

        rule: TransitionRule | None = TRANSITION_RULES.get(key)
        if rule is None:
            return False, f"Transition from '{from_column}' to '{to_column}' is not allowed."

        if actor_role not in rule.allowed_roles:
            return False, (
                f"Role '{actor_role}' cannot move tickets from '{from_column}' "
                f"to '{to_column}'.  Allowed: {', '.join(sorted(rule.allowed_roles))}."
            )

        for field_name in rule.prerequisites:
            if not getattr(ticket, field_name, None):
                return False, (
                    f"Prerequisite not met: '{field_name}' must be set before this transition."
                )

        return True, ""

    # ── Execution ────────────────────────────────────────────────────

    async def execute_transition(
        self,
        ticket: Ticket,
        to_column: str,
        actor_id: uuid.UUID,
        actor_role: str,
        db: AsyncSession,
        *,
        comment: str | None = None,
    ) -> Ticket:
        """Validate, execute the transition, record history, and trigger side effects.

        Raises :class:`ValueError` if the transition is invalid.
        """
        ok, reason = self.can_transition(ticket, to_column, actor_role)
        if not ok:
            raise ValueError(reason)

        from_column = (
            ticket.column_name.value
            if isinstance(ticket.column_name, ColumnName)
            else ticket.column_name
        )

        # Apply transition
        ticket.column_name = ColumnName(to_column)
        ticket.position = 0

        # Track retries
        if to_column == ColumnName.AI_CODING.value and from_column in (
            ColumnName.CODE_REVIEW.value,
            ColumnName.STAGING_VERIFICATION.value,
        ):
            ticket.retry_count += 1

        # Audit trail
        details: dict[str, Any] = {}
        if comment:
            details["comment"] = comment

        history = TicketHistory(
            ticket_id=ticket.id,
            actor_id=actor_id,
            actor_type="system" if actor_role == "ai_agent" else "user",
            action="moved",
            from_column=from_column,
            to_column=to_column,
            details=details or None,
        )
        db.add(history)
        await db.flush()
        await db.refresh(ticket)

        logger.info(
            "Ticket %s transitioned: %s -> %s (actor=%s role=%s)",
            ticket.id,
            from_column,
            to_column,
            actor_id,
            actor_role,
        )

        # Trigger side effects (non-blocking)
        await self._trigger_side_effects(ticket, from_column, to_column, db)

        return ticket

    # ── Side effects ─────────────────────────────────────────────────

    async def _trigger_side_effects(
        self,
        ticket: Ticket,
        from_column: str,
        to_column: str,
        db: AsyncSession,
    ) -> None:
        """Dispatch side effects based on the transition.

        Side effects are triggered asynchronously through n8n webhooks
        (or directly if n8n is not configured) so the transition returns
        immediately.
        """
        from app.services.n8n_service import trigger_workflow

        base_payload = {
            "ticket_id": str(ticket.id),
            "project_id": str(ticket.project_id),
            "from_column": from_column,
            "to_column": to_column,
            "ticket_title": ticket.title,
            "retry_count": ticket.retry_count,
        }

        try:
            if (
                from_column == ColumnName.BACKLOG.value
                and to_column == ColumnName.AI_PLANNING.value
            ):
                logger.info("Triggering AI planning for ticket %s", ticket.id)
                await trigger_workflow(
                    "ai_planning",
                    {
                        **base_payload,
                        "description": ticket.description or "",
                        "acceptance_criteria": ticket.acceptance_criteria or "",
                    },
                )

            elif (
                from_column == ColumnName.PLAN_REVIEW.value
                and to_column == ColumnName.AI_CODING.value
            ):
                logger.info("Triggering AI coding for ticket %s", ticket.id)
                await trigger_workflow("ai_coding", base_payload)

            elif (
                from_column == ColumnName.CODE_REVIEW.value
                and to_column == ColumnName.STAGING.value
            ):
                logger.info("Triggering CI/CD build+test for ticket %s", ticket.id)
                await trigger_workflow(
                    "build_test",
                    {
                        **base_payload,
                        "branch_name": ticket.branch_name or "",
                    },
                )

            elif (
                from_column == ColumnName.STAGING_VERIFICATION.value
                and to_column == ColumnName.PRODUCTION.value
            ):
                logger.info("Triggering canary deploy for ticket %s", ticket.id)
                await trigger_workflow(
                    "deploy_canary",
                    {
                        **base_payload,
                        "branch_name": ticket.branch_name or "",
                        "environment": "production",
                    },
                )

        except Exception as exc:
            # Side-effect failures should not block the transition.
            logger.error(
                "Side-effect trigger failed for %s -> %s on ticket %s: %s",
                from_column,
                to_column,
                ticket.id,
                exc,
            )
