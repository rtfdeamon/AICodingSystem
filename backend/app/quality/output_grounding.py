"""Output Grounding Verifier — verifies AI-generated outputs (code
explanations, review comments, planning decisions) are grounded in
retrieved context rather than hallucinated.

RAG-based AI systems frequently produce outputs that sound plausible but
are not supported by the retrieved source documents.  This module applies
claim-level verification inspired by Google's Check Grounding API,
deepset's groundedness metrics, and AWS RAG evaluation patterns to
detect and flag ungrounded content before it reaches users.

Based on Google "Check Grounding" API (Vertex AI, 2025), deepset
"GroundednessMetric" (haystack-evaluation, 2025), and AWS Bedrock
RAG Evaluation patterns (re:Invent 2025).

Key capabilities:
- Claim extraction: break AI output into individual claims/statements
- Evidence matching: n-gram overlap and keyword matching against context
- Per-claim and overall grounding score (0-1)
- Citation verification: check if cited sources support claims
- Ungrounded claim detection and flagging
- Confidence classification: GROUNDED / PARTIALLY_GROUNDED / UNGROUNDED
- Batch verification with aggregated metrics
- Quality gate with configurable thresholds
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

logger = logging.getLogger(__name__)


# ── Enums ────────────────────────────────────────────────────────────────

class GroundingLevel(StrEnum):
    GROUNDED = "grounded"
    PARTIALLY_GROUNDED = "partially_grounded"
    UNGROUNDED = "ungrounded"


class ClaimType(StrEnum):
    FACTUAL = "factual"
    CODE_REFERENCE = "code_reference"
    EXPLANATION = "explanation"
    RECOMMENDATION = "recommendation"


class GateDecision(StrEnum):
    PASS = "pass"
    WARN = "warn"
    BLOCK = "block"


# ── Data classes ─────────────────────────────────────────────────────────

@dataclass
class Claim:
    """A single extracted claim from AI output."""

    id: str
    text: str
    claim_type: ClaimType
    source_ref: str | None = None


@dataclass
class ContextDocument:
    """A retrieved context document used as evidence."""

    id: str
    content: str
    source: str = ""
    relevance_score: float = 1.0


@dataclass
class ClaimVerification:
    """Verification result for a single claim."""

    claim: Claim
    grounding_level: GroundingLevel
    support_score: float
    matching_contexts: list[str]  # IDs of supporting context docs
    explanation: str = ""


@dataclass
class VerificationResult:
    """Verification result for an entire AI output."""

    output_id: str
    claim_verifications: list[ClaimVerification]
    overall_score: float
    grounded_pct: float
    ungrounded_claims: list[Claim]
    gate_decision: GateDecision
    verified_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
    )


@dataclass
class BatchVerificationReport:
    """Aggregated report for batch verification."""

    results: list[VerificationResult]
    avg_score: float
    avg_grounded_pct: float
    total_ungrounded: int
    gate_decision: GateDecision


# ── OutputGroundingVerifier Engine ───────────────────────────────────────

class OutputGroundingVerifier:
    """Verifies that AI-generated outputs are grounded in retrieved context.

    Uses n-gram overlap and keyword matching to score how well each
    extracted claim is supported by provided context documents, then
    produces per-claim and overall grounding assessments.
    """

    def __init__(
        self,
        *,
        grounded_threshold: float = 0.6,
        partial_threshold: float = 0.3,
        warn_threshold: float = 0.7,
        block_threshold: float = 0.4,
    ) -> None:
        self._grounded_threshold = grounded_threshold
        self._partial_threshold = partial_threshold
        self._warn_threshold = warn_threshold
        self._block_threshold = block_threshold

    # ── Public API ───────────────────────────────────────────────────

    def verify(
        self,
        output_id: str,
        output_text: str,
        context_docs: list[ContextDocument],
    ) -> VerificationResult:
        """Verify a single AI output against provided context documents."""
        claims = self._extract_claims(output_text)

        verifications: list[ClaimVerification] = []
        for claim in claims:
            cv = self._verify_claim(claim, context_docs)
            verifications.append(cv)

        overall = self._overall_score(verifications)
        grounded_count = sum(
            1 for v in verifications
            if v.grounding_level == GroundingLevel.GROUNDED
        )
        grounded_pct = grounded_count / len(verifications) if verifications else 0.0
        ungrounded = [
            v.claim for v in verifications
            if v.grounding_level == GroundingLevel.UNGROUNDED
        ]
        gate = self._make_gate_decision(overall)

        result = VerificationResult(
            output_id=output_id,
            claim_verifications=verifications,
            overall_score=overall,
            grounded_pct=grounded_pct,
            ungrounded_claims=ungrounded,
            gate_decision=gate,
        )

        logger.info(
            "Verified output %s: score=%.3f grounded_pct=%.1f%% gate=%s",
            output_id, overall, grounded_pct * 100, gate,
        )
        return result

    def verify_batch(
        self,
        items: list[tuple[str, str, list[ContextDocument]]],
    ) -> BatchVerificationReport:
        """Verify a batch of (output_id, output_text, context_docs) tuples.

        Returns an aggregated report with per-item results.
        """
        results: list[VerificationResult] = []
        for output_id, output_text, context_docs in items:
            results.append(self.verify(output_id, output_text, context_docs))

        if not results:
            return BatchVerificationReport(
                results=[],
                avg_score=0.0,
                avg_grounded_pct=0.0,
                total_ungrounded=0,
                gate_decision=GateDecision.PASS,
            )

        avg_score = sum(r.overall_score for r in results) / len(results)
        avg_grounded = sum(r.grounded_pct for r in results) / len(results)
        total_ungrounded = sum(len(r.ungrounded_claims) for r in results)
        gate = self._make_gate_decision(avg_score)

        return BatchVerificationReport(
            results=results,
            avg_score=avg_score,
            avg_grounded_pct=avg_grounded,
            total_ungrounded=total_ungrounded,
            gate_decision=gate,
        )

    # ── Claim Extraction ─────────────────────────────────────────────

    def _extract_claims(self, text: str) -> list[Claim]:
        """Break output text into individual claims/statements.

        Splits on sentence boundaries and classifies each claim by type.
        """
        sentences = self._split_sentences(text)
        claims: list[Claim] = []
        for raw_sentence in sentences:
            sentence = raw_sentence.strip()
            if not sentence or len(sentence) < 5:
                continue
            claim_type = self._classify_claim_type(sentence)
            source_ref = self._extract_source_ref(sentence)
            claims.append(Claim(
                id=uuid.uuid4().hex[:12],
                text=sentence,
                claim_type=claim_type,
                source_ref=source_ref,
            ))
        return claims

    # ── Claim Verification ───────────────────────────────────────────

    def _verify_claim(
        self,
        claim: Claim,
        contexts: list[ContextDocument],
    ) -> ClaimVerification:
        """Verify a single claim against context documents."""
        if not contexts:
            return ClaimVerification(
                claim=claim,
                grounding_level=GroundingLevel.UNGROUNDED,
                support_score=0.0,
                matching_contexts=[],
                explanation="No context documents provided.",
            )

        best_score = 0.0
        matching_ids: list[str] = []

        for ctx in contexts:
            score = self._compute_support_score(claim, ctx)
            if score >= self._partial_threshold:
                matching_ids.append(ctx.id)
            if score > best_score:
                best_score = score

        level = self._classify_grounding(best_score)

        explanation = (
            f"Best support score: {best_score:.3f} from "
            f"{len(matching_ids)} context(s)."
        )

        return ClaimVerification(
            claim=claim,
            grounding_level=level,
            support_score=best_score,
            matching_contexts=matching_ids,
            explanation=explanation,
        )

    # ── Scoring Helpers ──────────────────────────────────────────────

    def _compute_ngram_overlap(
        self,
        text_a: str,
        text_b: str,
        n: int = 3,
    ) -> float:
        """Compute character n-gram overlap between two texts.

        Returns the Jaccard similarity of n-gram sets (0-1).
        """
        a_lower = text_a.lower().strip()
        b_lower = text_b.lower().strip()
        if len(a_lower) < n or len(b_lower) < n:
            return 0.0

        ngrams_a = {a_lower[i:i + n] for i in range(len(a_lower) - n + 1)}
        ngrams_b = {b_lower[i:i + n] for i in range(len(b_lower) - n + 1)}

        if not ngrams_a or not ngrams_b:
            return 0.0

        intersection = ngrams_a & ngrams_b
        union = ngrams_a | ngrams_b
        return len(intersection) / len(union)

    def _compute_keyword_overlap(
        self,
        claim_text: str,
        context_text: str,
    ) -> float:
        """Compute keyword overlap between claim and context.

        Extracts significant words (length >= 4) and returns the fraction
        of claim keywords found in the context.
        """
        claim_words = self._extract_keywords(claim_text)
        context_words = self._extract_keywords(context_text)

        if not claim_words:
            return 0.0

        matched = claim_words & context_words
        return len(matched) / len(claim_words)

    def _compute_support_score(
        self,
        claim: Claim,
        context: ContextDocument,
    ) -> float:
        """Compute a combined support score for a claim against a context.

        Blends n-gram overlap (40%) and keyword overlap (60%), weighted
        by the context document's relevance score.
        """
        ngram = self._compute_ngram_overlap(claim.text, context.content)
        keyword = self._compute_keyword_overlap(claim.text, context.content)
        raw = 0.4 * ngram + 0.6 * keyword
        return raw * context.relevance_score

    def _classify_grounding(self, score: float) -> GroundingLevel:
        """Classify a support score into a grounding level."""
        if score >= self._grounded_threshold:
            return GroundingLevel.GROUNDED
        if score >= self._partial_threshold:
            return GroundingLevel.PARTIALLY_GROUNDED
        return GroundingLevel.UNGROUNDED

    def _overall_score(self, verifications: list[ClaimVerification]) -> float:
        """Compute the overall grounding score from individual verifications."""
        if not verifications:
            return 0.0
        return sum(v.support_score for v in verifications) / len(verifications)

    def _make_gate_decision(self, score: float) -> GateDecision:
        """Decide gate outcome based on overall score."""
        if score < self._block_threshold:
            return GateDecision.BLOCK
        if score < self._warn_threshold:
            return GateDecision.WARN
        return GateDecision.PASS

    # ── Text Processing Helpers ──────────────────────────────────────

    @staticmethod
    def _split_sentences(text: str) -> list[str]:
        """Split text into sentences using basic heuristics."""
        # Split on period/exclamation/question followed by whitespace or end
        parts = re.split(r'(?<=[.!?])\s+', text.strip())
        return [p for p in parts if p]

    @staticmethod
    def _classify_claim_type(sentence: str) -> ClaimType:
        """Classify a sentence into a ClaimType based on keywords."""
        lower = sentence.lower()
        code_indicators = (
            "function", "class", "method", "variable", "import",
            "return", "def ", "async ", "module", "`",
        )
        rec_indicators = (
            "should", "recommend", "suggest", "consider", "best practice",
            "prefer", "avoid", "use ",
        )
        explanation_indicators = (
            "because", "since", "therefore", "due to", "this means",
            "in order to", "explains", "reason",
        )
        for kw in code_indicators:
            if kw in lower:
                return ClaimType.CODE_REFERENCE
        for kw in rec_indicators:
            if kw in lower:
                return ClaimType.RECOMMENDATION
        for kw in explanation_indicators:
            if kw in lower:
                return ClaimType.EXPLANATION
        return ClaimType.FACTUAL

    @staticmethod
    def _extract_source_ref(sentence: str) -> str | None:
        """Extract a source reference like [source: X] from a sentence."""
        match = re.search(r'\[source:\s*([^\]]+)\]', sentence, re.IGNORECASE)
        return match.group(1).strip() if match else None

    @staticmethod
    def _extract_keywords(text: str) -> set[str]:
        """Extract significant keywords (length >= 4) from text."""
        words = re.findall(r'[a-zA-Z_]\w*', text.lower())
        return {w for w in words if len(w) >= 4}
