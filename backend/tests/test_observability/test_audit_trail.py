"""Tests for the immutable audit trail module."""

from __future__ import annotations

import time

import pytest

from app.observability.audit_trail import (
    AuditAction,
    AuditEntry,
    AuditQuery,
    AuditSeverity,
    AuditTrail,
)


@pytest.fixture()
def trail() -> AuditTrail:
    return AuditTrail()


# -- Recording entries -------------------------------------------------------


class TestRecordEntry:
    def test_record_returns_audit_entry(self, trail: AuditTrail) -> None:
        entry = trail.record(
            action=AuditAction.CODE_GENERATED,
            actor="claude_agent",
            target="app/main.py",
        )
        assert isinstance(entry, AuditEntry)

    def test_record_populates_fields(self, trail: AuditTrail) -> None:
        entry = trail.record(
            action=AuditAction.REVIEW_COMPLETED,
            actor="review_agent",
            target="PR-42",
            details={"findings": 3},
            severity=AuditSeverity.WARNING,
            outcome="issues_found",
        )
        assert entry.action == AuditAction.REVIEW_COMPLETED
        assert entry.actor == "review_agent"
        assert entry.target == "PR-42"
        assert entry.details == {"findings": 3}
        assert entry.severity == AuditSeverity.WARNING
        assert entry.outcome == "issues_found"
        assert len(entry.entry_id) == 32
        assert entry.timestamp > 0

    def test_record_defaults(self, trail: AuditTrail) -> None:
        entry = trail.record(
            action=AuditAction.AGENT_INVOKED,
            actor="system",
            target="pipeline",
        )
        assert entry.severity == AuditSeverity.INFO
        assert entry.outcome == "success"
        assert entry.details == {}

    def test_record_generates_unique_ids(self, trail: AuditTrail) -> None:
        e1 = trail.record(action=AuditAction.AGENT_INVOKED, actor="a", target="t")
        e2 = trail.record(action=AuditAction.AGENT_INVOKED, actor="a", target="t")
        assert e1.entry_id != e2.entry_id


# -- Hash chain integrity ---------------------------------------------------


class TestHashChain:
    def test_first_entry_has_zero_previous_hash(self, trail: AuditTrail) -> None:
        entry = trail.record(
            action=AuditAction.PLAN_CREATED,
            actor="planner",
            target="sprint-1",
        )
        assert entry.previous_hash == "0" * 64

    def test_second_entry_chains_to_first(self, trail: AuditTrail) -> None:
        e1 = trail.record(action=AuditAction.AGENT_INVOKED, actor="a", target="t")
        e2 = trail.record(action=AuditAction.CODE_GENERATED, actor="b", target="u")
        assert e2.previous_hash == e1.entry_hash

    def test_hash_is_sha256_hex(self, trail: AuditTrail) -> None:
        entry = trail.record(
            action=AuditAction.TEST_EXECUTED,
            actor="ci",
            target="test_suite",
        )
        assert len(entry.entry_hash) == 64
        # Verify it's valid hex
        int(entry.entry_hash, 16)

    def test_verify_integrity_valid_chain(self, trail: AuditTrail) -> None:
        for i in range(5):
            trail.record(
                action=AuditAction.CODE_GENERATED,
                actor=f"agent_{i}",
                target=f"file_{i}.py",
            )
        valid, errors = trail.verify_integrity()
        assert valid is True
        assert errors == []

    def test_verify_integrity_detects_tampered_hash(self, trail: AuditTrail) -> None:
        trail.record(action=AuditAction.AGENT_INVOKED, actor="a", target="t1")
        trail.record(action=AuditAction.CODE_GENERATED, actor="b", target="t2")
        trail.record(action=AuditAction.REVIEW_COMPLETED, actor="c", target="t3")

        # Tamper with the middle entry's hash by replacing it in the list
        original = trail._entries[1]
        tampered = AuditEntry(
            entry_id=original.entry_id,
            timestamp=original.timestamp,
            action=original.action,
            actor="TAMPERED_ACTOR",
            target=original.target,
            details=original.details,
            severity=original.severity,
            outcome=original.outcome,
            previous_hash=original.previous_hash,
            entry_hash=original.entry_hash,
        )
        trail._entries[1] = tampered

        valid, errors = trail.verify_integrity()
        assert valid is False
        assert len(errors) >= 1

    def test_verify_integrity_detects_broken_chain_link(self, trail: AuditTrail) -> None:
        trail.record(action=AuditAction.AGENT_INVOKED, actor="a", target="t1")
        trail.record(action=AuditAction.CODE_GENERATED, actor="b", target="t2")

        # Break the chain by modifying previous_hash of second entry
        original = trail._entries[1]
        broken = AuditEntry(
            entry_id=original.entry_id,
            timestamp=original.timestamp,
            action=original.action,
            actor=original.actor,
            target=original.target,
            details=original.details,
            severity=original.severity,
            outcome=original.outcome,
            previous_hash="bad_hash",
            entry_hash=original.entry_hash,
        )
        trail._entries[1] = broken

        valid, errors = trail.verify_integrity()
        assert valid is False
        assert any("previous_hash mismatch" in e for e in errors)


# -- Querying ----------------------------------------------------------------


class TestQuery:
    def _populate(self, trail: AuditTrail) -> list[AuditEntry]:
        """Create a set of diverse entries for query tests."""
        entries = []
        entries.append(
            trail.record(
                action=AuditAction.AGENT_INVOKED,
                actor="alice",
                target="pipeline",
                severity=AuditSeverity.INFO,
            )
        )
        entries.append(
            trail.record(
                action=AuditAction.CODE_GENERATED,
                actor="bob",
                target="main.py",
                severity=AuditSeverity.WARNING,
            )
        )
        entries.append(
            trail.record(
                action=AuditAction.ESCALATION_RAISED,
                actor="alice",
                target="security_issue",
                severity=AuditSeverity.CRITICAL,
            )
        )
        entries.append(
            trail.record(
                action=AuditAction.CONFIG_CHANGED,
                actor="admin",
                target="settings",
                severity=AuditSeverity.SECURITY,
            )
        )
        return entries

    def test_query_all(self, trail: AuditTrail) -> None:
        self._populate(trail)
        results = trail.query(AuditQuery())
        assert len(results) == 4

    def test_query_by_actor(self, trail: AuditTrail) -> None:
        self._populate(trail)
        results = trail.query(AuditQuery(actor="alice"))
        assert len(results) == 2
        assert all(e.actor == "alice" for e in results)

    def test_query_by_action(self, trail: AuditTrail) -> None:
        self._populate(trail)
        results = trail.query(AuditQuery(action=AuditAction.CODE_GENERATED))
        assert len(results) == 1
        assert results[0].action == AuditAction.CODE_GENERATED

    def test_query_by_severity(self, trail: AuditTrail) -> None:
        self._populate(trail)
        results = trail.query(AuditQuery(severity=AuditSeverity.CRITICAL))
        assert len(results) == 1
        assert results[0].severity == AuditSeverity.CRITICAL

    def test_query_by_time_range(self, trail: AuditTrail) -> None:
        trail.record(action=AuditAction.AGENT_INVOKED, actor="a", target="t")
        after_first = time.time()
        # Small sleep to ensure distinct timestamps
        time.sleep(0.01)
        e2 = trail.record(action=AuditAction.CODE_GENERATED, actor="b", target="u")

        results = trail.query(AuditQuery(start_time=after_first))
        assert len(results) == 1
        assert results[0].entry_id == e2.entry_id

    def test_query_respects_limit(self, trail: AuditTrail) -> None:
        for i in range(10):
            trail.record(action=AuditAction.AGENT_INVOKED, actor="a", target=f"t{i}")
        results = trail.query(AuditQuery(limit=3))
        assert len(results) == 3

    def test_query_combined_filters(self, trail: AuditTrail) -> None:
        self._populate(trail)
        results = trail.query(
            AuditQuery(actor="alice", severity=AuditSeverity.CRITICAL)
        )
        assert len(results) == 1
        assert results[0].action == AuditAction.ESCALATION_RAISED


# -- Export ------------------------------------------------------------------


class TestExport:
    def test_export_all_entries(self, trail: AuditTrail) -> None:
        trail.record(action=AuditAction.AGENT_INVOKED, actor="a", target="t1")
        trail.record(action=AuditAction.CODE_GENERATED, actor="b", target="t2")
        exported = trail.export_entries()
        assert len(exported) == 2
        assert all(isinstance(e, dict) for e in exported)

    def test_export_contains_all_fields(self, trail: AuditTrail) -> None:
        trail.record(
            action=AuditAction.DEPLOYMENT_TRIGGERED,
            actor="deployer",
            target="production",
            details={"version": "1.0"},
            severity=AuditSeverity.CRITICAL,
            outcome="success",
        )
        exported = trail.export_entries()
        entry = exported[0]
        assert entry["action"] == AuditAction.DEPLOYMENT_TRIGGERED
        assert entry["actor"] == "deployer"
        assert entry["target"] == "production"
        assert entry["details"] == {"version": "1.0"}
        assert entry["severity"] == AuditSeverity.CRITICAL
        assert entry["entry_hash"]
        assert entry["previous_hash"]

    def test_export_by_time_range(self, trail: AuditTrail) -> None:
        trail.record(action=AuditAction.AGENT_INVOKED, actor="a", target="t1")
        after_first = time.time()
        time.sleep(0.01)
        trail.record(action=AuditAction.CODE_GENERATED, actor="b", target="t2")

        exported = trail.export_entries(start_time=after_first)
        assert len(exported) == 1
        assert exported[0]["actor"] == "b"


# -- Stats -------------------------------------------------------------------


class TestStats:
    def test_stats_empty_trail(self, trail: AuditTrail) -> None:
        stats = trail.get_stats()
        assert stats["total_entries"] == 0
        assert stats["actions"] == {}
        assert stats["severities"] == {}
        assert stats["actors"] == {}
        assert stats["first_entry"] is None
        assert stats["last_entry"] is None

    def test_stats_counts(self, trail: AuditTrail) -> None:
        trail.record(action=AuditAction.AGENT_INVOKED, actor="alice", target="t1")
        trail.record(action=AuditAction.AGENT_INVOKED, actor="alice", target="t2")
        trail.record(action=AuditAction.CODE_GENERATED, actor="bob", target="t3")

        stats = trail.get_stats()
        assert stats["total_entries"] == 3
        assert stats["actions"][AuditAction.AGENT_INVOKED] == 2
        assert stats["actions"][AuditAction.CODE_GENERATED] == 1
        assert stats["actors"]["alice"] == 2
        assert stats["actors"]["bob"] == 1
        assert stats["first_entry"] is not None
        assert stats["last_entry"] is not None
        assert stats["last_entry"] >= stats["first_entry"]


# -- Ordering & edge cases --------------------------------------------------


class TestEdgeCases:
    def test_empty_trail_verify_integrity(self, trail: AuditTrail) -> None:
        valid, errors = trail.verify_integrity()
        assert valid is True
        assert errors == []

    def test_single_entry_verify_integrity(self, trail: AuditTrail) -> None:
        trail.record(action=AuditAction.AGENT_INVOKED, actor="a", target="t")
        valid, errors = trail.verify_integrity()
        assert valid is True
        assert errors == []

    def test_entries_are_ordered_by_insertion(self, trail: AuditTrail) -> None:
        for i in range(5):
            trail.record(
                action=AuditAction.AGENT_INVOKED,
                actor=f"agent_{i}",
                target=f"target_{i}",
            )
        results = trail.query(AuditQuery())
        for i in range(len(results) - 1):
            assert results[i].timestamp <= results[i + 1].timestamp

    def test_empty_trail_query_returns_empty(self, trail: AuditTrail) -> None:
        results = trail.query(AuditQuery(actor="nobody"))
        assert results == []

    def test_empty_trail_export_returns_empty(self, trail: AuditTrail) -> None:
        exported = trail.export_entries()
        assert exported == []

    def test_compute_hash_deterministic(self) -> None:
        h1 = AuditTrail._compute_hash("test_data")
        h2 = AuditTrail._compute_hash("test_data")
        assert h1 == h2

    def test_compute_hash_different_inputs(self) -> None:
        h1 = AuditTrail._compute_hash("data_a")
        h2 = AuditTrail._compute_hash("data_b")
        assert h1 != h2


# -- Enum values -------------------------------------------------------------


class TestEnums:
    def test_audit_action_values(self) -> None:
        assert AuditAction.AGENT_INVOKED == "agent_invoked"
        assert AuditAction.FINDING_DISMISSED == "finding_dismissed"
        assert AuditAction.APPROVAL_GRANTED == "approval_granted"
        assert len(AuditAction) == 10

    def test_audit_severity_values(self) -> None:
        assert AuditSeverity.INFO == "info"
        assert AuditSeverity.SECURITY == "security"
        assert len(AuditSeverity) == 4
