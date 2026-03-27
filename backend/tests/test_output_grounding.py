"""Tests for Output Grounding Verifier engine."""

from __future__ import annotations

import pytest

from app.quality.output_grounding import (
    BatchVerificationReport,
    Claim,
    ClaimType,
    ContextDocument,
    GateDecision,
    GroundingLevel,
    OutputGroundingVerifier,
    VerificationResult,
)


@pytest.fixture
def verifier() -> OutputGroundingVerifier:
    return OutputGroundingVerifier()


@pytest.fixture
def sample_contexts() -> list[ContextDocument]:
    return [
        ContextDocument(
            id="ctx-1",
            content="The function parse_config reads a YAML file and returns a dictionary. "
                    "It handles missing files by raising FileNotFoundError.",
            source="config_parser.py",
            relevance_score=1.0,
        ),
        ContextDocument(
            id="ctx-2",
            content="Python dataclasses provide a decorator for automatically adding "
                    "generated special methods such as __init__ and __repr__ to classes.",
            source="python_docs",
            relevance_score=0.9,
        ),
        ContextDocument(
            id="ctx-3",
            content="The retry mechanism uses exponential backoff with a maximum of "
                    "five attempts before raising a TimeoutError.",
            source="retry_module.py",
            relevance_score=0.8,
        ),
    ]


def _make_context(content: str, doc_id: str = "ctx-1", relevance: float = 1.0) -> ContextDocument:
    return ContextDocument(id=doc_id, content=content, source="test", relevance_score=relevance)


# ── Claim Extraction ─────────────────────────────────────────────────────

class TestClaimExtraction:
    def test_single_sentence(self, verifier: OutputGroundingVerifier) -> None:
        claims = verifier._extract_claims("The function returns a dictionary.")
        assert len(claims) == 1
        assert "dictionary" in claims[0].text

    def test_multiple_sentences(self, verifier: OutputGroundingVerifier) -> None:
        text = "First claim here. Second claim here. Third claim here."
        claims = verifier._extract_claims(text)
        assert len(claims) == 3

    def test_empty_text(self, verifier: OutputGroundingVerifier) -> None:
        claims = verifier._extract_claims("")
        assert claims == []

    def test_short_fragments_filtered(self, verifier: OutputGroundingVerifier) -> None:
        text = "OK. Yes. The function returns a value."
        claims = verifier._extract_claims(text)
        # "OK" and "Yes" are too short (< 5 chars)
        assert len(claims) == 1

    def test_claim_type_code_reference(self, verifier: OutputGroundingVerifier) -> None:
        claims = verifier._extract_claims("The function parse_config handles errors.")
        assert claims[0].claim_type == ClaimType.CODE_REFERENCE

    def test_claim_type_recommendation(self, verifier: OutputGroundingVerifier) -> None:
        claims = verifier._extract_claims("You should prefer smaller commits for this pattern.")
        assert claims[0].claim_type == ClaimType.RECOMMENDATION

    def test_claim_type_explanation(self, verifier: OutputGroundingVerifier) -> None:
        claims = verifier._extract_claims("This works since the retry logic handles all timeouts.")
        assert claims[0].claim_type == ClaimType.EXPLANATION

    def test_claim_type_factual(self, verifier: OutputGroundingVerifier) -> None:
        claims = verifier._extract_claims("Python was created in 1991.")
        assert claims[0].claim_type == ClaimType.FACTUAL

    def test_source_ref_extraction(self, verifier: OutputGroundingVerifier) -> None:
        claims = verifier._extract_claims(
            "The parser handles YAML files [source: config_parser.py]."
        )
        assert claims[0].source_ref == "config_parser.py"

    def test_no_source_ref(self, verifier: OutputGroundingVerifier) -> None:
        claims = verifier._extract_claims("The parser handles YAML files.")
        assert claims[0].source_ref is None


# ── N-gram Overlap ───────────────────────────────────────────────────────

class TestNgramOverlap:
    def test_identical_texts(self, verifier: OutputGroundingVerifier) -> None:
        score = verifier._compute_ngram_overlap("hello world", "hello world")
        assert score == 1.0

    def test_completely_different(self, verifier: OutputGroundingVerifier) -> None:
        score = verifier._compute_ngram_overlap("aaa bbb ccc", "xxx yyy zzz")
        assert score == 0.0

    def test_partial_overlap(self, verifier: OutputGroundingVerifier) -> None:
        score = verifier._compute_ngram_overlap(
            "the function returns a dict",
            "the function raises an error",
        )
        assert 0.0 < score < 1.0

    def test_short_text_below_n(self, verifier: OutputGroundingVerifier) -> None:
        score = verifier._compute_ngram_overlap("ab", "ab", n=3)
        assert score == 0.0

    def test_case_insensitive(self, verifier: OutputGroundingVerifier) -> None:
        score = verifier._compute_ngram_overlap("Hello World", "hello world")
        assert score == 1.0


# ── Keyword Overlap ──────────────────────────────────────────────────────

class TestKeywordOverlap:
    def test_full_overlap(self, verifier: OutputGroundingVerifier) -> None:
        score = verifier._compute_keyword_overlap(
            "function returns dictionary value",
            "the function returns a dictionary value from config",
        )
        assert score == 1.0

    def test_no_overlap(self, verifier: OutputGroundingVerifier) -> None:
        score = verifier._compute_keyword_overlap(
            "quantum entanglement theory",
            "the function parses yaml configuration files",
        )
        assert score == 0.0

    def test_partial_overlap(self, verifier: OutputGroundingVerifier) -> None:
        score = verifier._compute_keyword_overlap(
            "function handles errors gracefully",
            "the function reads configuration data",
        )
        assert 0.0 < score < 1.0

    def test_empty_claim(self, verifier: OutputGroundingVerifier) -> None:
        score = verifier._compute_keyword_overlap("no", "some long context here")
        assert score == 0.0


# ── Support Score ────────────────────────────────────────────────────────

class TestSupportScore:
    def test_high_support(self, verifier: OutputGroundingVerifier) -> None:
        claim = Claim(
            id="c1",
            text="The function parse_config reads a YAML file and returns a dict.",
            claim_type=ClaimType.FACTUAL,
        )
        ctx = _make_context(
            "The function parse_config reads a YAML file and returns a dict.",
        )
        score = verifier._compute_support_score(claim, ctx)
        assert score >= 0.8

    def test_low_support(self, verifier: OutputGroundingVerifier) -> None:
        claim = Claim(
            id="c1",
            text="Quantum computing uses qubits for parallel processing.",
            claim_type=ClaimType.FACTUAL,
        )
        ctx = _make_context("The function parse_config reads a YAML file.")
        score = verifier._compute_support_score(claim, ctx)
        assert score < 0.3

    def test_relevance_weight(self, verifier: OutputGroundingVerifier) -> None:
        claim = Claim(
            id="c1",
            text="The function parse_config reads a YAML file.",
            claim_type=ClaimType.FACTUAL,
        )
        ctx_high = _make_context("The function parse_config reads a YAML file.", relevance=1.0)
        ctx_low = _make_context("The function parse_config reads a YAML file.", relevance=0.5)
        score_high = verifier._compute_support_score(claim, ctx_high)
        score_low = verifier._compute_support_score(claim, ctx_low)
        assert score_high > score_low


# ── Grounding Classification ────────────────────────────────────────────

class TestGroundingClassification:
    def test_grounded(self, verifier: OutputGroundingVerifier) -> None:
        assert verifier._classify_grounding(0.8) == GroundingLevel.GROUNDED

    def test_partially_grounded(self, verifier: OutputGroundingVerifier) -> None:
        assert verifier._classify_grounding(0.45) == GroundingLevel.PARTIALLY_GROUNDED

    def test_ungrounded(self, verifier: OutputGroundingVerifier) -> None:
        assert verifier._classify_grounding(0.1) == GroundingLevel.UNGROUNDED

    def test_boundary_grounded(self, verifier: OutputGroundingVerifier) -> None:
        assert verifier._classify_grounding(0.6) == GroundingLevel.GROUNDED

    def test_boundary_partial(self, verifier: OutputGroundingVerifier) -> None:
        assert verifier._classify_grounding(0.3) == GroundingLevel.PARTIALLY_GROUNDED


# ── Gate Decision ────────────────────────────────────────────────────────

class TestGateDecision:
    def test_pass(self, verifier: OutputGroundingVerifier) -> None:
        assert verifier._make_gate_decision(0.8) == GateDecision.PASS

    def test_warn(self, verifier: OutputGroundingVerifier) -> None:
        assert verifier._make_gate_decision(0.5) == GateDecision.WARN

    def test_block(self, verifier: OutputGroundingVerifier) -> None:
        assert verifier._make_gate_decision(0.2) == GateDecision.BLOCK

    def test_boundary_pass(self, verifier: OutputGroundingVerifier) -> None:
        assert verifier._make_gate_decision(0.7) == GateDecision.PASS

    def test_boundary_block(self, verifier: OutputGroundingVerifier) -> None:
        assert verifier._make_gate_decision(0.4) == GateDecision.WARN


# ── Verify (Integration) ────────────────────────────────────────────────

class TestVerify:
    def test_grounded_output(
        self,
        verifier: OutputGroundingVerifier,
        sample_contexts: list[ContextDocument],
    ) -> None:
        text = "The function parse_config reads a YAML file and returns a dictionary."
        result = verifier.verify("out-1", text, sample_contexts)
        assert isinstance(result, VerificationResult)
        assert result.output_id == "out-1"
        assert 0.0 <= result.overall_score <= 1.0

    def test_ungrounded_output(
        self,
        verifier: OutputGroundingVerifier,
        sample_contexts: list[ContextDocument],
    ) -> None:
        text = "Quantum entanglement enables faster-than-light communication."
        result = verifier.verify("out-2", text, sample_contexts)
        assert len(result.ungrounded_claims) >= 1

    def test_no_context_all_ungrounded(self, verifier: OutputGroundingVerifier) -> None:
        text = "The function returns data. It handles errors properly."
        result = verifier.verify("out-3", text, [])
        assert result.overall_score == 0.0
        assert len(result.ungrounded_claims) == 2
        assert result.gate_decision == GateDecision.BLOCK

    def test_timestamp_present(
        self,
        verifier: OutputGroundingVerifier,
        sample_contexts: list[ContextDocument],
    ) -> None:
        result = verifier.verify("out-4", "Some claim here.", sample_contexts)
        assert "T" in result.verified_at

    def test_grounded_pct_range(
        self,
        verifier: OutputGroundingVerifier,
        sample_contexts: list[ContextDocument],
    ) -> None:
        text = "The function parse_config reads a YAML file."
        result = verifier.verify("out-5", text, sample_contexts)
        assert 0.0 <= result.grounded_pct <= 1.0


# ── Batch Verification ──────────────────────────────────────────────────

class TestBatchVerification:
    def test_batch_empty(self, verifier: OutputGroundingVerifier) -> None:
        report = verifier.verify_batch([])
        assert isinstance(report, BatchVerificationReport)
        assert report.avg_score == 0.0
        assert report.total_ungrounded == 0

    def test_batch_multiple(
        self,
        verifier: OutputGroundingVerifier,
        sample_contexts: list[ContextDocument],
    ) -> None:
        items = [
            ("out-1", "The function parse_config reads a YAML file.", sample_contexts),
            ("out-2", "Quantum computing uses qubits.", sample_contexts),
        ]
        report = verifier.verify_batch(items)
        assert len(report.results) == 2
        assert 0.0 <= report.avg_score <= 1.0

    def test_batch_aggregated_ungrounded(
        self,
        verifier: OutputGroundingVerifier,
    ) -> None:
        items = [
            ("out-1", "Aliens built the pyramids.", []),
            ("out-2", "Time travel is possible via wormholes.", []),
        ]
        report = verifier.verify_batch(items)
        assert report.total_ungrounded >= 2
        assert report.gate_decision == GateDecision.BLOCK


# ── Custom Thresholds ───────────────────────────────────────────────────

class TestCustomThresholds:
    def test_strict_thresholds(self, sample_contexts: list[ContextDocument]) -> None:
        strict = OutputGroundingVerifier(
            grounded_threshold=0.9,
            partial_threshold=0.7,
            warn_threshold=0.9,
            block_threshold=0.8,
        )
        text = "The function parse_config reads a YAML file."
        result = strict.verify("out-1", text, sample_contexts)
        # With very strict thresholds, fewer claims will be classified as grounded
        assert isinstance(result.gate_decision, GateDecision)

    def test_lenient_thresholds(self, sample_contexts: list[ContextDocument]) -> None:
        lenient = OutputGroundingVerifier(
            grounded_threshold=0.1,
            partial_threshold=0.05,
            warn_threshold=0.1,
            block_threshold=0.05,
        )
        text = "The function parse_config reads a YAML file."
        result = lenient.verify("out-1", text, sample_contexts)
        assert result.gate_decision == GateDecision.PASS
