"""Tests for Multi-Agent Workspace Coordinator."""

from __future__ import annotations

from app.quality.multi_agent_workspace import (
    ConflictSeverity,
    CoordinatorConfig,
    GateDecision,
    MergeOutcome,
    MultiAgentWorkspaceCoordinator,
    WorkspaceStatus,
    _classify_conflict,
    _compute_similarity,
    _detect_duplication,
    _detect_file_conflicts,
    _gate_from_conflicts,
)

# ── Helper factories ──────────────────────────────────────────────────────


def _make_coordinator(**overrides) -> MultiAgentWorkspaceCoordinator:
    config = CoordinatorConfig(**overrides) if overrides else None
    return MultiAgentWorkspaceCoordinator(config)


# ── Pure helper tests ─────────────────────────────────────────────────────


class TestDetectFileConflicts:
    def test_no_overlap(self):
        assert _detect_file_conflicts(["a.py"], ["b.py"]) == []

    def test_overlap(self):
        result = _detect_file_conflicts(
            ["a.py", "b.py"], ["b.py", "c.py"],
        )
        assert result == ["b.py"]

    def test_empty(self):
        assert _detect_file_conflicts([], []) == []

    def test_full_overlap(self):
        result = _detect_file_conflicts(
            ["a.py", "b.py"], ["a.py", "b.py"],
        )
        assert len(result) == 2


class TestClassifyConflict:
    def test_no_overlap(self):
        assert _classify_conflict([], {}) == ConflictSeverity.NONE

    def test_owned_file(self):
        severity = _classify_conflict(
            ["a.py"],
            {"a.py": "agent-1"},
        )
        assert severity == ConflictSeverity.HUMAN_REQUIRED

    def test_small_overlap(self):
        severity = _classify_conflict(["a.py"], {})
        assert severity == ConflictSeverity.AUTO_RESOLVABLE

    def test_large_overlap(self):
        severity = _classify_conflict(
            ["a.py", "b.py", "c.py"], {},
        )
        assert severity == ConflictSeverity.AI_RESOLVABLE


class TestComputeSimilarity:
    def test_identical(self):
        tokens = {"a", "b", "c"}
        assert _compute_similarity(tokens, tokens) == 1.0

    def test_no_overlap(self):
        assert _compute_similarity({"a"}, {"b"}) == 0.0

    def test_partial(self):
        sim = _compute_similarity({"a", "b", "c"}, {"b", "c", "d"})
        assert 0.4 < sim < 0.6

    def test_empty(self):
        assert _compute_similarity(set(), set()) == 0.0


class TestDetectDuplication:
    def test_high_similarity(self):
        alert = _detect_duplication(
            "def foo(): return 1",
            "def foo(): return 1",
            "agent-1", "agent-2",
            "a.py", "b.py",
            threshold=0.5,
        )
        assert alert is not None
        assert alert.similarity >= 0.5

    def test_low_similarity(self):
        alert = _detect_duplication(
            "def foo(): return 1",
            "class Bar: pass",
            "agent-1", "agent-2",
            "a.py", "b.py",
            threshold=0.7,
        )
        assert alert is None

    def test_exact_threshold(self):
        alert = _detect_duplication(
            "hello world",
            "hello world",
            "a", "b", "f1", "f2",
            threshold=1.0,
        )
        assert alert is not None


class TestGateFromConflicts:
    def test_no_conflicts(self):
        assert _gate_from_conflicts(0, 0) == GateDecision.PASS

    def test_all_resolved(self):
        assert _gate_from_conflicts(0, 5) == GateDecision.WARN

    def test_unresolved(self):
        assert _gate_from_conflicts(2, 5) == GateDecision.BLOCK


# ── Coordinator class tests ──────────────────────────────────────────────


class TestCreateWorkspace:
    def test_basic_creation(self):
        c = _make_coordinator()
        wid, msg = c.create_workspace("agent-1")
        assert wid
        ws = c.get_workspace(wid)
        assert ws.agent_id == "agent-1"
        assert ws.status == WorkspaceStatus.ACTIVE

    def test_custom_branch(self):
        c = _make_coordinator()
        wid, _ = c.create_workspace(
            "agent-1", branch_name="feature/auth",
        )
        ws = c.get_workspace(wid)
        assert ws.branch_name == "feature/auth"

    def test_max_concurrent(self):
        c = _make_coordinator(max_concurrent_agents=2)
        c.create_workspace("a1")
        c.create_workspace("a2")
        wid, msg = c.create_workspace("a3")
        assert not wid
        assert "max" in msg.lower()


class TestAssignOwnership:
    def test_assign(self):
        c = _make_coordinator()
        ok, conflicts = c.assign_ownership(
            "agent-1", ["src/auth.py"],
        )
        assert ok
        assert len(conflicts) == 0

    def test_conflict(self):
        c = _make_coordinator()
        c.assign_ownership("agent-1", ["src/auth.py"])
        ok, conflicts = c.assign_ownership(
            "agent-2", ["src/auth.py"],
        )
        assert not ok
        assert len(conflicts) == 1

    def test_same_agent_ok(self):
        c = _make_coordinator()
        c.assign_ownership("agent-1", ["src/auth.py"])
        ok, _ = c.assign_ownership("agent-1", ["src/auth.py"])
        assert ok


class TestRegisterChanges:
    def test_register(self):
        c = _make_coordinator()
        wid, _ = c.create_workspace("agent-1")
        ok, msg = c.register_changes(wid, ["src/main.py"])
        assert ok

    def test_ownership_violation(self):
        c = _make_coordinator(enable_ownership_checks=True)
        c.assign_ownership("agent-1", ["src/auth.py"])
        wid, _ = c.create_workspace("agent-2")
        ok, msg = c.register_changes(wid, ["src/auth.py"])
        assert not ok

    def test_not_found(self):
        c = _make_coordinator()
        ok, _ = c.register_changes("nope", [])
        assert not ok


class TestRequestMerge:
    def test_no_conflict(self):
        c = _make_coordinator()
        wid1, _ = c.create_workspace("a1")
        wid2, _ = c.create_workspace("a2")
        c.register_changes(wid1, ["a.py"])
        c.register_changes(wid2, ["b.py"])
        mr = c.request_merge(wid1)
        assert mr.outcome == MergeOutcome.SUCCESS

    def test_conflict_escalated(self):
        c = _make_coordinator()
        c.assign_ownership("a1", ["shared.py"])
        wid1, _ = c.create_workspace("a1")
        wid2, _ = c.create_workspace("a2")
        c.register_changes(wid1, ["shared.py"])
        c.register_changes(wid2, ["shared.py"])
        mr = c.request_merge(wid1)
        assert mr.outcome == MergeOutcome.ESCALATED
        assert len(mr.conflicts) > 0

    def test_auto_resolve(self):
        c = _make_coordinator(auto_resolve_non_overlapping=True)
        wid1, _ = c.create_workspace("a1")
        wid2, _ = c.create_workspace("a2")
        c.register_changes(wid1, ["a.py"])
        c.register_changes(wid2, ["a.py"])
        mr = c.request_merge(wid1)
        assert mr.outcome == MergeOutcome.AUTO_RESOLVED

    def test_not_found(self):
        c = _make_coordinator()
        mr = c.request_merge("nope")
        assert mr.outcome == MergeOutcome.BLOCKED


class TestCheckDuplication:
    def test_detected(self):
        c = _make_coordinator(duplication_threshold=0.5)
        alert = c.check_duplication(
            "a1", "def helper(): return True", "utils_a.py",
            "a2", "def helper(): return True", "utils_b.py",
        )
        assert alert is not None

    def test_not_detected(self):
        c = _make_coordinator(duplication_threshold=0.9)
        alert = c.check_duplication(
            "a1", "import os", "a.py",
            "a2", "class Foo: pass", "b.py",
        )
        assert alert is None


class TestCoordinatorReport:
    def test_empty(self):
        c = _make_coordinator()
        report = c.coordinator_report()
        assert report.total_workspaces == 0
        assert report.gate == GateDecision.PASS

    def test_with_workspaces(self):
        c = _make_coordinator()
        wid1, _ = c.create_workspace("a1")
        wid2, _ = c.create_workspace("a2")
        c.register_changes(wid1, ["a.py"])
        c.request_merge(wid1)
        report = c.coordinator_report()
        assert report.total_workspaces == 2
        assert report.merged == 1
        assert report.active == 1
