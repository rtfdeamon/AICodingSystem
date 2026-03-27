"""Immutable Audit Trail for AI Agent Actions.

Provides tamper-evident logging of all AI agent operations with hash-chain
integrity verification, compliance querying, and export capabilities.

Every audit entry includes a SHA-256 hash that chains to the previous entry,
making it possible to detect any retroactive modification of the log.
"""

from __future__ import annotations

import hashlib
import logging
import time
import uuid
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


# -- Action & Severity Enums ------------------------------------------------


class AuditAction(StrEnum):
    """Auditable actions performed by AI agents."""

    AGENT_INVOKED = "agent_invoked"
    CODE_GENERATED = "code_generated"
    REVIEW_COMPLETED = "review_completed"
    PLAN_CREATED = "plan_created"
    TEST_EXECUTED = "test_executed"
    DEPLOYMENT_TRIGGERED = "deployment_triggered"
    ESCALATION_RAISED = "escalation_raised"
    FINDING_DISMISSED = "finding_dismissed"
    APPROVAL_GRANTED = "approval_granted"
    CONFIG_CHANGED = "config_changed"


class AuditSeverity(StrEnum):
    """Severity levels for audit entries."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    SECURITY = "security"


# -- Data Classes ------------------------------------------------------------


@dataclass(frozen=True)
class AuditEntry:
    """A single immutable audit log entry.

    The ``entry_hash`` field is a SHA-256 digest computed over the entry's
    core fields plus the ``previous_hash``, forming a hash chain.
    """

    entry_id: str
    timestamp: float
    action: AuditAction
    actor: str
    target: str
    details: dict[str, Any]
    severity: AuditSeverity
    outcome: str
    previous_hash: str
    entry_hash: str


@dataclass
class AuditQuery:
    """Filter criteria for querying the audit trail."""

    start_time: float | None = None
    end_time: float | None = None
    actor: str | None = None
    action: AuditAction | None = None
    severity: AuditSeverity | None = None
    limit: int = 100


# -- Audit Trail -------------------------------------------------------------


class AuditTrail:
    """In-memory, hash-chained audit trail for AI agent operations.

    Usage::

        trail = AuditTrail()
        entry = trail.record(
            action=AuditAction.CODE_GENERATED,
            actor="claude_agent",
            target="backend/app/main.py",
            details={"lines_added": 42},
            severity=AuditSeverity.INFO,
            outcome="success",
        )
        ok, errors = trail.verify_integrity()
        assert ok
    """

    def __init__(self) -> None:
        self._entries: list[AuditEntry] = []

    # -- Public API ----------------------------------------------------------

    def record(
        self,
        action: AuditAction,
        actor: str,
        target: str,
        details: dict[str, Any] | None = None,
        severity: AuditSeverity = AuditSeverity.INFO,
        outcome: str = "success",
    ) -> AuditEntry:
        """Record a new audit entry and append it to the chain.

        Returns the newly created :class:`AuditEntry`.
        """
        entry_id = uuid.uuid4().hex
        timestamp = time.time()
        previous_hash = self._entries[-1].entry_hash if self._entries else "0" * 64

        entry_hash = self._compute_hash(
            f"{entry_id}{timestamp}{action}{actor}{target}{previous_hash}"
        )

        entry = AuditEntry(
            entry_id=entry_id,
            timestamp=timestamp,
            action=action,
            actor=actor,
            target=target,
            details=details if details is not None else {},
            severity=severity,
            outcome=outcome,
            previous_hash=previous_hash,
            entry_hash=entry_hash,
        )

        self._entries.append(entry)

        logger.info(
            "Audit entry recorded: action=%s actor=%s target=%s outcome=%s",
            action,
            actor,
            target,
            outcome,
        )

        return entry

    def query(self, audit_query: AuditQuery) -> list[AuditEntry]:
        """Return entries matching the given query filters."""
        results = list(self._entries)

        if audit_query.start_time is not None:
            results = [e for e in results if e.timestamp >= audit_query.start_time]
        if audit_query.end_time is not None:
            results = [e for e in results if e.timestamp <= audit_query.end_time]
        if audit_query.actor is not None:
            results = [e for e in results if e.actor == audit_query.actor]
        if audit_query.action is not None:
            results = [e for e in results if e.action == audit_query.action]
        if audit_query.severity is not None:
            results = [e for e in results if e.severity == audit_query.severity]

        return results[: audit_query.limit]

    def verify_integrity(self) -> tuple[bool, list[str]]:
        """Verify the hash chain of all entries.

        Returns a tuple of ``(is_valid, errors)`` where *errors* is a list
        of human-readable descriptions of any integrity violations found.
        """
        errors: list[str] = []

        for idx, entry in enumerate(self._entries):
            # Check previous_hash linkage
            expected_prev = "0" * 64 if idx == 0 else self._entries[idx - 1].entry_hash

            if entry.previous_hash != expected_prev:
                errors.append(
                    f"Entry {idx} ({entry.entry_id}): previous_hash mismatch "
                    f"(expected {expected_prev[:16]}..., got {entry.previous_hash[:16]}...)"
                )

            # Recompute and verify entry_hash
            expected_hash = self._compute_hash(
                f"{entry.entry_id}{entry.timestamp}{entry.action}"
                f"{entry.actor}{entry.target}{entry.previous_hash}"
            )
            if entry.entry_hash != expected_hash:
                errors.append(
                    f"Entry {idx} ({entry.entry_id}): entry_hash mismatch "
                    f"(expected {expected_hash[:16]}..., got {entry.entry_hash[:16]}...)"
                )

        return (len(errors) == 0, errors)

    def export_entries(
        self,
        start_time: float | None = None,
        end_time: float | None = None,
    ) -> list[dict[str, Any]]:
        """Export entries as JSON-serialisable dicts for compliance audits."""
        entries = self._entries

        if start_time is not None:
            entries = [e for e in entries if e.timestamp >= start_time]
        if end_time is not None:
            entries = [e for e in entries if e.timestamp <= end_time]

        return [asdict(e) for e in entries]

    def get_stats(self) -> dict[str, Any]:
        """Return summary statistics about the audit trail."""
        if not self._entries:
            return {
                "total_entries": 0,
                "actions": {},
                "severities": {},
                "actors": {},
                "first_entry": None,
                "last_entry": None,
            }

        action_counts: dict[str, int] = {}
        severity_counts: dict[str, int] = {}
        actor_counts: dict[str, int] = {}

        for entry in self._entries:
            action_counts[entry.action] = action_counts.get(entry.action, 0) + 1
            severity_counts[entry.severity] = severity_counts.get(entry.severity, 0) + 1
            actor_counts[entry.actor] = actor_counts.get(entry.actor, 0) + 1

        return {
            "total_entries": len(self._entries),
            "actions": action_counts,
            "severities": severity_counts,
            "actors": actor_counts,
            "first_entry": self._entries[0].timestamp,
            "last_entry": self._entries[-1].timestamp,
        }

    # -- Internal ------------------------------------------------------------

    @staticmethod
    def _compute_hash(entry_data: str) -> str:
        """Compute a SHA-256 hex digest for the given data string."""
        return hashlib.sha256(entry_data.encode("utf-8")).hexdigest()
