"""Tests for Agent Entropy Collector (best practice #59)."""

from __future__ import annotations

from app.quality.agent_entropy_collector import (
    AgentEntropyCollector,
    BatchEntropyReport,
    ContextEntry,
    EntropySeverity,
    EntropyType,
    GateDecision,
    PruneAction,
    SessionEntropyReport,
)

# ── Helpers ──────────────────────────────────────────────────────────────

def _make_entry(
    id: str = "e1",
    content: str = "Do something",
    entry_type: str = "instruction",
    access_count: int = 5,
    tokens: int = 0,
) -> ContextEntry:
    return ContextEntry(
        id=id,
        content=content,
        entry_type=entry_type,
        access_count=access_count,
        tokens_estimate=tokens,
    )


def _make_entries(n: int, prefix: str = "entry", content_fn=None) -> list[ContextEntry]:
    entries = []
    for i in range(n):
        content = content_fn(i) if content_fn else f"Instruction number {i} for the agent"
        entries.append(_make_entry(
            id=f"{prefix}_{i}",
            content=content,
            access_count=i,
        ))
    return entries


# ── Init tests ───────────────────────────────────────────────────────────

class TestAgentEntropyCollectorInit:
    def test_default_init(self):
        collector = AgentEntropyCollector()
        assert collector.max_context_tokens == 100_000
        assert collector.warn_entropy == 0.4

    def test_custom_init(self):
        collector = AgentEntropyCollector(
            max_context_tokens=50_000,
            warn_entropy=0.3,
        )
        assert collector.max_context_tokens == 50_000


# ── Empty session tests ─────────────────────────────────────────────────

class TestEmptySession:
    def test_empty_entries(self):
        collector = AgentEntropyCollector()
        report = collector.analyze("s1", [])
        assert isinstance(report, SessionEntropyReport)
        assert report.entropy_score == 0.0
        assert report.gate_decision == GateDecision.PASS
        assert report.total_entries == 0


# ── Fingerprint and similarity tests ────────────────────────────────────

class TestFingerprint:
    def test_same_content_same_fingerprint(self):
        fp1 = AgentEntropyCollector._fingerprint("hello world")
        fp2 = AgentEntropyCollector._fingerprint("hello world")
        assert fp1 == fp2

    def test_normalized_fingerprint(self):
        fp1 = AgentEntropyCollector._fingerprint("Hello  World")
        fp2 = AgentEntropyCollector._fingerprint("hello world")
        assert fp1 == fp2

    def test_different_content(self):
        fp1 = AgentEntropyCollector._fingerprint("hello")
        fp2 = AgentEntropyCollector._fingerprint("world")
        assert fp1 != fp2


class TestSimilarity:
    def test_identical(self):
        sim = AgentEntropyCollector._similarity("hello world", "hello world")
        assert sim == 1.0

    def test_no_overlap(self):
        sim = AgentEntropyCollector._similarity("hello world", "foo bar")
        assert sim == 0.0

    def test_partial_overlap(self):
        sim = AgentEntropyCollector._similarity("hello world foo", "hello world bar")
        assert 0.0 < sim < 1.0

    def test_empty(self):
        sim = AgentEntropyCollector._similarity("", "hello")
        assert sim == 0.0


class TestTokenEstimate:
    def test_basic(self):
        tokens = AgentEntropyCollector._estimate_tokens("hello world")
        assert tokens >= 1

    def test_empty(self):
        tokens = AgentEntropyCollector._estimate_tokens("")
        assert tokens == 1  # minimum 1


# ── Duplication detection tests ─────────────────────────────────────────

class TestDuplication:
    def test_exact_duplicates_found(self):
        collector = AgentEntropyCollector()
        entries = [
            _make_entry("e1", "Always use TypeScript for frontend code"),
            _make_entry("e2", "Always use TypeScript for frontend code"),
            _make_entry("e3", "Different instruction here"),
        ]
        report = collector.analyze("s1", entries)
        dup_findings = [f for f in report.findings if f.entropy_type == EntropyType.DUPLICATION]
        assert len(dup_findings) >= 1

    def test_no_duplicates(self):
        collector = AgentEntropyCollector()
        entries = _make_entries(5)
        report = collector.analyze("s1", entries)
        dup_findings = [f for f in report.findings if f.entropy_type == EntropyType.DUPLICATION]
        assert len(dup_findings) == 0

    def test_prune_recommendation_for_duplicate(self):
        collector = AgentEntropyCollector()
        entries = [
            _make_entry("e1", "Always format code with prettier"),
            _make_entry("e2", "Always format code with prettier"),
        ]
        report = collector.analyze("s1", entries)
        remove_recs = [r for r in report.prune_recommendations if r.action == PruneAction.REMOVE]
        assert len(remove_recs) >= 1


# ── Staleness detection tests ──────────────────────────────────────────

class TestStaleness:
    def test_stale_entries_detected(self):
        collector = AgentEntropyCollector(stale_threshold_accesses=0)
        entries = [
            _make_entry("e1", "Old instruction", access_count=0),
            _make_entry("e2", "Another old one", access_count=0),
            _make_entry("e3", "Third old one", access_count=0),
            _make_entry("e4", "Active instruction", access_count=5),
        ]
        report = collector.analyze("s1", entries)
        stale_findings = [
            f for f in report.findings
            if f.entropy_type == EntropyType.STALE_REFERENCE
        ]
        assert len(stale_findings) >= 1

    def test_stale_ratio(self):
        collector = AgentEntropyCollector(stale_threshold_accesses=0)
        entries = [
            _make_entry("e1", "Old", access_count=0),
            _make_entry("e2", "Old too", access_count=0),
            _make_entry("e3", "Old also", access_count=0),
            _make_entry("e4", "Active", access_count=5),
        ]
        report = collector.analyze("s1", entries)
        assert report.stale_ratio == 0.75

    def test_no_stale(self):
        collector = AgentEntropyCollector(stale_threshold_accesses=0)
        entries = [
            _make_entry("e1", "Active", access_count=5),
            _make_entry("e2", "Also active", access_count=3),
        ]
        report = collector.analyze("s1", entries)
        assert report.stale_ratio == 0.0


# ── Context bloat tests ────────────────────────────────────────────────

class TestContextBloat:
    def test_bloat_detected(self):
        collector = AgentEntropyCollector(max_context_tokens=100)
        entries = [
            _make_entry("e1", "x" * 400, tokens=100),  # ~100 tokens each, 3 = 300 > 70% of 100
            _make_entry("e2", "y" * 400, tokens=100),
            _make_entry("e3", "z" * 400, tokens=100),
        ]
        report = collector.analyze("s1", entries)
        bloat_findings = [f for f in report.findings if f.entropy_type == EntropyType.CONTEXT_BLOAT]
        assert len(bloat_findings) >= 1

    def test_no_bloat(self):
        collector = AgentEntropyCollector(max_context_tokens=100_000)
        entries = _make_entries(3)
        report = collector.analyze("s1", entries)
        bloat_findings = [f for f in report.findings if f.entropy_type == EntropyType.CONTEXT_BLOAT]
        assert len(bloat_findings) == 0


# ── Contradiction detection tests ──────────────────────────────────────

class TestContradictions:
    def test_contradiction_detected(self):
        collector = AgentEntropyCollector()
        entries = [
            _make_entry("e1", "Always use tabs for code indentation formatting"),
            _make_entry("e2", "Never use tabs for code indentation formatting"),
        ]
        report = collector.analyze("s1", entries)
        contra_findings = [
            f for f in report.findings
            if f.entropy_type == EntropyType.CONTRADICTION
        ]
        assert len(contra_findings) >= 1

    def test_no_contradiction(self):
        collector = AgentEntropyCollector()
        entries = [
            _make_entry("e1", "Use Python for backend development"),
            _make_entry("e2", "Use TypeScript for frontend development"),
        ]
        report = collector.analyze("s1", entries)
        contra_findings = [
            f for f in report.findings
            if f.entropy_type == EntropyType.CONTRADICTION
        ]
        assert len(contra_findings) == 0

    def test_enable_disable_contradiction(self):
        collector = AgentEntropyCollector()
        entries = [
            _make_entry("e1", "Enable logging for the database service module"),
            _make_entry("e2", "Disable logging for the database service module"),
        ]
        report = collector.analyze("s1", entries)
        contra = [f for f in report.findings if f.entropy_type == EntropyType.CONTRADICTION]
        assert len(contra) >= 1


# ── Instruction overload tests ─────────────────────────────────────────

class TestInstructionOverload:
    def test_overload_detected(self):
        collector = AgentEntropyCollector()
        entries = _make_entries(60)
        report = collector.analyze("s1", entries)
        overload = [
            f for f in report.findings
            if f.entropy_type == EntropyType.INSTRUCTION_OVERLOAD
        ]
        assert len(overload) >= 1

    def test_no_overload(self):
        collector = AgentEntropyCollector()
        entries = _make_entries(10)
        report = collector.analyze("s1", entries)
        overload = [
            f for f in report.findings
            if f.entropy_type == EntropyType.INSTRUCTION_OVERLOAD
        ]
        assert len(overload) == 0


# ── Entropy scoring tests ──────────────────────────────────────────────

class TestEntropyScoring:
    def test_low_entropy_clean_session(self):
        collector = AgentEntropyCollector()
        entries = _make_entries(5, content_fn=lambda i: f"Unique instruction {i} for task {i * 2}")
        for e in entries:
            e.access_count = 5
        report = collector.analyze("s1", entries)
        assert report.entropy_score < 0.3
        assert report.severity in (EntropySeverity.LOW, EntropySeverity.MEDIUM)

    def test_high_entropy_messy_session(self):
        collector = AgentEntropyCollector(max_context_tokens=500)
        entries = []
        # Lots of duplicates, stale entries, and bloat
        for i in range(20):
            entries.append(_make_entry(
                f"e{i}",
                "Repeated instruction for the project" if i % 2 == 0 else f"Unique instruction {i}",
                access_count=0,
                tokens=30,
            ))
        report = collector.analyze("s1", entries)
        assert report.entropy_score > 0.3

    def test_unique_content_ratio(self):
        collector = AgentEntropyCollector()
        entries = [
            _make_entry("e1", "Same content same content", access_count=5),
            _make_entry("e2", "Same content same content", access_count=5),
            _make_entry("e3", "Different content here", access_count=5),
        ]
        report = collector.analyze("s1", entries)
        assert report.unique_content_ratio < 1.0


# ── Gate decision tests ─────────────────────────────────────────────────

class TestGateDecisions:
    def test_pass_on_clean(self):
        collector = AgentEntropyCollector()
        entries = _make_entries(3, content_fn=lambda i: f"Unique content {i}")
        for e in entries:
            e.access_count = 5
        report = collector.analyze("s1", entries)
        assert report.gate_decision == GateDecision.PASS

    def test_compact_on_high_entropy(self):
        collector = AgentEntropyCollector(
            max_context_tokens=200,
            compact_entropy=0.5,
        )
        entries = []
        for i in range(30):
            entries.append(_make_entry(
                f"e{i}",
                "Repeated content for the system" if i % 3 == 0 else f"Stuff {i}",
                access_count=0,
                tokens=10,
            ))
        report = collector.analyze("s1", entries)
        # Should trigger at least WARN or COMPACT
        assert report.gate_decision in (GateDecision.WARN, GateDecision.COMPACT)


# ── Batch analysis tests ────────────────────────────────────────────────

class TestBatchAnalysis:
    def test_batch_multiple_sessions(self):
        collector = AgentEntropyCollector()
        sessions = [
            ("s1", _make_entries(5, content_fn=lambda i: f"Session 1 instruction {i}")),
            ("s2", _make_entries(5, content_fn=lambda i: f"Session 2 instruction {i}")),
        ]
        for _, entries in sessions:
            for e in entries:
                e.access_count = 5
        report = collector.batch_analyze(sessions)
        assert isinstance(report, BatchEntropyReport)
        assert report.total_sessions == 2

    def test_batch_empty(self):
        collector = AgentEntropyCollector()
        report = collector.batch_analyze([])
        assert report.total_sessions == 0
        assert report.gate_decision == GateDecision.PASS


# ── History tests ────────────────────────────────────────────────────────

class TestHistory:
    def test_history_recorded(self):
        collector = AgentEntropyCollector()
        collector.analyze("s1", _make_entries(3))
        collector.analyze("s2", _make_entries(3))
        assert len(collector.history) == 2

    def test_history_immutable(self):
        collector = AgentEntropyCollector()
        collector.analyze("s1", _make_entries(3))
        h = collector.history
        h.clear()
        assert len(collector.history) == 1


# ── Report field tests ──────────────────────────────────────────────────

class TestReportFields:
    def test_report_fields_populated(self):
        collector = AgentEntropyCollector()
        entries = _make_entries(5)
        report = collector.analyze("s1", entries)
        assert report.session_id == "s1"
        assert report.total_entries == 5
        assert report.total_tokens > 0
        assert report.analyzed_at
        assert 0.0 <= report.unique_content_ratio <= 1.0
        assert 0.0 <= report.stale_ratio <= 1.0
        assert 0.0 <= report.entropy_score <= 1.0
