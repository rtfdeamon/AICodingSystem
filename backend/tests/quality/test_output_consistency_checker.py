"""Tests for Output Consistency Checker."""

from __future__ import annotations

from app.quality.output_consistency_checker import (
    BatchConsistencyReport,
    ConsistencyConfig,
    ConsistencyGrade,
    GateDecision,
    OutputConsistencyChecker,
    OutputRecord,
    _category_agreement,
    _compute_pairwise_jaccard,
    _gate_from_grade,
    _grade_consistency,
    _hash_prompt,
    _jaccard_similarity,
    _tokenize,
)

# ── _hash_prompt ─────────────────────────────────────────────────────

class TestHashPrompt:
    def test_deterministic(self):
        h1 = _hash_prompt("hello world")
        h2 = _hash_prompt("hello world")
        assert h1 == h2

    def test_different_inputs(self):
        h1 = _hash_prompt("hello")
        h2 = _hash_prompt("world")
        assert h1 != h2

    def test_length(self):
        h = _hash_prompt("test")
        assert len(h) == 16


# ── _tokenize ────────────────────────────────────────────────────────

class TestTokenize:
    def test_basic(self):
        tokens = _tokenize("hello world")
        assert tokens == {"hello", "world"}

    def test_case_insensitive(self):
        tokens = _tokenize("Hello World")
        assert tokens == {"hello", "world"}

    def test_empty(self):
        tokens = _tokenize("")
        assert tokens == set() or tokens == {""}


# ── _jaccard_similarity ──────────────────────────────────────────────

class TestJaccardSimilarity:
    def test_identical(self):
        assert _jaccard_similarity({"a", "b"}, {"a", "b"}) == 1.0

    def test_disjoint(self):
        assert _jaccard_similarity({"a"}, {"b"}) == 0.0

    def test_partial(self):
        sim = _jaccard_similarity({"a", "b", "c"}, {"a", "b", "d"})
        assert 0.4 < sim < 0.6  # 2/4 = 0.5

    def test_empty_both(self):
        assert _jaccard_similarity(set(), set()) == 1.0

    def test_one_empty(self):
        assert _jaccard_similarity({"a"}, set()) == 0.0


# ── _compute_pairwise_jaccard ────────────────────────────────────────

class TestPairwiseJaccard:
    def test_single_output(self):
        assert _compute_pairwise_jaccard(["hello"]) == 1.0

    def test_identical_outputs(self):
        assert _compute_pairwise_jaccard(["a b c", "a b c", "a b c"]) == 1.0

    def test_different_outputs(self):
        sim = _compute_pairwise_jaccard(["a b c", "x y z"])
        assert sim == 0.0

    def test_partial_overlap(self):
        sim = _compute_pairwise_jaccard(["a b c", "a b d"])
        assert 0.3 < sim < 0.7


# ── _category_agreement ──────────────────────────────────────────────

class TestCategoryAgreement:
    def test_empty(self):
        assert _category_agreement([]) == 1.0

    def test_unanimous(self):
        assert _category_agreement(["approve", "approve", "approve"]) == 1.0

    def test_split(self):
        pct = _category_agreement(["approve", "reject", "approve"])
        assert abs(pct - 2 / 3) < 0.01

    def test_all_different(self):
        pct = _category_agreement(["a", "b", "c"])
        assert abs(pct - 1 / 3) < 0.01


# ── _grade_consistency ───────────────────────────────────────────────

class TestGradeConsistency:
    def test_deterministic(self):
        assert _grade_consistency(0.96, ConsistencyConfig()) == ConsistencyGrade.DETERMINISTIC

    def test_acceptable(self):
        assert _grade_consistency(0.80, ConsistencyConfig()) == ConsistencyGrade.ACCEPTABLE

    def test_volatile(self):
        assert _grade_consistency(0.55, ConsistencyConfig()) == ConsistencyGrade.VOLATILE

    def test_unstable(self):
        assert _grade_consistency(0.30, ConsistencyConfig()) == ConsistencyGrade.UNSTABLE


# ── _gate_from_grade ─────────────────────────────────────────────────

class TestGateFromGrade:
    def test_pass(self):
        assert _gate_from_grade(ConsistencyGrade.DETERMINISTIC) == GateDecision.PASS
        assert _gate_from_grade(ConsistencyGrade.ACCEPTABLE) == GateDecision.PASS

    def test_warn(self):
        assert _gate_from_grade(ConsistencyGrade.VOLATILE) == GateDecision.WARN

    def test_block(self):
        assert _gate_from_grade(ConsistencyGrade.UNSTABLE) == GateDecision.BLOCK


# ── OutputConsistencyChecker ─────────────────────────────────────────

class TestOutputConsistencyChecker:
    def test_record_output(self):
        c = OutputConsistencyChecker()
        rec = c.record_output("Generate code for fizzbuzz", "claude", "def fizzbuzz():", "code")
        assert isinstance(rec, OutputRecord)
        assert rec.agent == "claude"

    def test_record_output_by_hash(self):
        c = OutputConsistencyChecker()
        rec = c.record_output_by_hash("abc123", "claude", "output", "cat")
        assert rec.prompt_hash == "abc123"

    def test_evaluate_insufficient_samples(self):
        c = OutputConsistencyChecker()
        c.record_output("test", "claude", "out1")
        score = c.evaluate_prompt(_hash_prompt("test"), "claude")
        assert score.grade == ConsistencyGrade.DETERMINISTIC  # not enough to evaluate

    def test_evaluate_consistent(self):
        c = OutputConsistencyChecker()
        for _ in range(5):
            c.record_output("write fizzbuzz", "claude", "def fizzbuzz(): pass", "code")
        score = c.evaluate_prompt(_hash_prompt("write fizzbuzz"), "claude")
        assert score.determinism_score >= 0.95
        assert score.grade == ConsistencyGrade.DETERMINISTIC

    def test_evaluate_inconsistent(self):
        c = OutputConsistencyChecker()
        outputs = [
            "def fizzbuzz(): pass",
            "function fizzbuzz() { return 42; }",
            "SELECT * FROM fizzbuzz",
            "print('hello world')",
        ]
        categories = ["python", "javascript", "sql", "python"]
        for out, cat in zip(outputs, categories, strict=False):
            c.record_output("write fizzbuzz", "claude", out, cat)
        score = c.evaluate_prompt(_hash_prompt("write fizzbuzz"), "claude")
        assert score.determinism_score < 0.75
        assert score.grade in {ConsistencyGrade.VOLATILE, ConsistencyGrade.UNSTABLE}

    def test_evaluate_partial_consistency(self):
        c = OutputConsistencyChecker()
        for _ in range(3):
            c.record_output("task", "claude", "def foo(): return 1", "code")
        c.record_output("task", "claude", "def bar(): return 2", "code")
        score = c.evaluate_prompt(_hash_prompt("task"), "claude")
        assert 0.5 < score.determinism_score < 1.0

    def test_find_hotspots(self):
        c = OutputConsistencyChecker()
        # Consistent prompt
        for _ in range(5):
            c.record_output("consistent", "claude", "same output", "ok")
        # Inconsistent prompt
        for i in range(5):
            c.record_output("volatile", "claude", f"output_{i}", f"cat_{i}")
        hotspots = c.find_hotspots()
        assert len(hotspots) >= 1
        # Most volatile should be first
        assert hotspots[0].determinism_score < 0.9

    def test_find_hotspots_empty(self):
        c = OutputConsistencyChecker()
        assert c.find_hotspots() == []

    def test_batch_evaluate(self):
        c = OutputConsistencyChecker()
        for _ in range(5):
            c.record_output("p1", "claude", "output1", "cat1")
            c.record_output("p2", "gpt4", "output2", "cat2")
        report = c.batch_evaluate()
        assert isinstance(report, BatchConsistencyReport)
        assert report.total_prompts == 2
        assert report.total_records == 10

    def test_batch_overall_determinism(self):
        c = OutputConsistencyChecker()
        for _ in range(5):
            c.record_output("p1", "claude", "same", "ok")
        report = c.batch_evaluate()
        assert report.overall_determinism >= 0.95
        assert report.overall_grade == ConsistencyGrade.DETERMINISTIC

    def test_category_agreement_tracked(self):
        c = OutputConsistencyChecker()
        for _ in range(4):
            c.record_output("task", "claude", "output text here", "approve")
        c.record_output("task", "claude", "different output text", "reject")
        score = c.evaluate_prompt(_hash_prompt("task"), "claude")
        assert score.category_agreement_pct == 80.0

    def test_no_categories(self):
        c = OutputConsistencyChecker()
        for _ in range(5):
            c.record_output("task", "claude", "same output")
        score = c.evaluate_prompt(_hash_prompt("task"), "claude")
        assert score.category_agreement_pct == 100.0

    def test_custom_config(self):
        cfg = ConsistencyConfig(
            deterministic_threshold=0.99,
            acceptable_threshold=0.90,
            volatile_threshold=0.70,
            min_samples=5,
        )
        c = OutputConsistencyChecker(cfg)
        for _ in range(5):
            c.record_output("task", "claude", "same output", "ok")
        score = c.evaluate_prompt(_hash_prompt("task"), "claude")
        assert score.grade == ConsistencyGrade.DETERMINISTIC

    def test_hotspot_unique_categories(self):
        c = OutputConsistencyChecker()
        for i in range(5):
            c.record_output("volatile", "claude", f"output_{i}", f"cat_{i}")
        hotspots = c.find_hotspots()
        assert hotspots[0].unique_categories == 5

    def test_multiple_agents_same_prompt(self):
        c = OutputConsistencyChecker()
        for _ in range(5):
            c.record_output("task", "claude", "output_a", "ok")
            c.record_output("task", "gpt4", "output_b", "ok")
        # Each agent should be evaluated separately
        score_claude = c.evaluate_prompt(_hash_prompt("task"), "claude")
        score_gpt4 = c.evaluate_prompt(_hash_prompt("task"), "gpt4")
        assert score_claude.determinism_score >= 0.95
        assert score_gpt4.determinism_score >= 0.95

    def test_gate_pass_for_consistent(self):
        c = OutputConsistencyChecker()
        for _ in range(5):
            c.record_output("task", "claude", "consistent output", "ok")
        score = c.evaluate_prompt(_hash_prompt("task"), "claude")
        assert score.gate == GateDecision.PASS

    def test_gate_block_for_unstable(self):
        c = OutputConsistencyChecker(ConsistencyConfig(min_samples=3))
        for i in range(5):
            c.record_output("task", "claude", f"totally different {i} output words", f"cat_{i}")
        score = c.evaluate_prompt(_hash_prompt("task"), "claude")
        assert score.gate in {GateDecision.WARN, GateDecision.BLOCK}
