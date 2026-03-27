"""Multi-Model Review Router — route code review tasks to different models
based on change type, complexity, and domain.

In 2026, leading AI code review tools use multiple models for different tasks,
optimizing for the specific strengths of each. A typical multi-model
architecture uses a lightweight classifier for initial pass to categorize
changes and route them to appropriate analyzers.

Based on 2026 AI code review trends: CodeRabbit, Qodo, Augment Code multi-model
architectures; system-aware vs diff-aware review routing.

Key capabilities:
- Change classifier: categorize diffs by type (security, logic, refactor, style, etc.)
- Model profile registry: capabilities, cost, latency per model
- Cost-aware routing: balance quality vs cost
- Complexity-based routing: simple changes → fast model, complex → capable model
- Domain routing: security changes → security-specialized model
- Review aggregation: merge findings from multiple model reviews
- Routing analytics: track which models review what and their effectiveness
- Quality gate: configurable minimum model capability for change type
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

logger = logging.getLogger(__name__)


# ── Enums ────────────────────────────────────────────────────────────────

class ChangeCategory(StrEnum):
    SECURITY = "security"
    LOGIC = "logic"
    REFACTOR = "refactor"
    STYLE = "style"
    DOCUMENTATION = "documentation"
    TESTS = "tests"
    DEPENDENCY = "dependency"
    CONFIG = "config"
    PERFORMANCE = "performance"
    API = "api"


class ReviewDepth(StrEnum):
    SHALLOW = "shallow"
    STANDARD = "standard"
    DEEP = "deep"


class ModelTier(StrEnum):
    FAST = "fast"
    STANDARD = "standard"
    PREMIUM = "premium"


class GateDecision(StrEnum):
    PASS = "pass"
    WARN = "warn"
    BLOCK = "block"


# ── Category keywords ───────────────────────────────────────────────────

_CATEGORY_KEYWORDS: dict[ChangeCategory, list[str]] = {
    ChangeCategory.SECURITY: [
        "auth", "password", "token", "secret", "crypto", "hash",
        "encrypt", "decrypt", "permission", "rbac", "jwt", "oauth",
        "sanitize", "escape", "injection", "xss", "csrf", "cors",
        "ssl", "tls", "certificate", "credential",
    ],
    ChangeCategory.LOGIC: [
        "algorithm", "calculate", "compute", "process", "transform",
        "validate", "parse", "convert", "filter", "sort", "merge",
        "aggregate", "reduce", "resolve", "evaluate",
    ],
    ChangeCategory.REFACTOR: [
        "rename", "extract", "move", "reorganize", "simplify",
        "cleanup", "restructure", "decouple", "abstract",
    ],
    ChangeCategory.STYLE: [
        "format", "indent", "whitespace", "lint", "prettier",
        "eslint", "ruff", "black", "isort",
    ],
    ChangeCategory.DOCUMENTATION: [
        "readme", "docs", "docstring", "comment", "changelog",
        "license", "contributing",
    ],
    ChangeCategory.TESTS: [
        "test", "spec", "fixture", "mock", "stub", "assert",
        "expect", "describe", "pytest", "jest", "vitest",
    ],
    ChangeCategory.DEPENDENCY: [
        "requirements", "package.json", "pyproject", "cargo.toml",
        "go.mod", "gemfile", "pom.xml", "build.gradle",
        "dependency", "upgrade", "version",
    ],
    ChangeCategory.CONFIG: [
        "config", "settings", "env", "docker", "kubernetes",
        "nginx", "terraform", "ansible", "yaml", "toml",
    ],
    ChangeCategory.PERFORMANCE: [
        "cache", "index", "query", "optimize", "benchmark",
        "latency", "throughput", "memory", "cpu", "profile",
    ],
    ChangeCategory.API: [
        "endpoint", "route", "handler", "controller", "middleware",
        "request", "response", "schema", "serializer", "api",
    ],
}

# ── Category → minimum model tier ────────────────────────────────────────

_MIN_TIER: dict[ChangeCategory, ModelTier] = {
    ChangeCategory.SECURITY: ModelTier.PREMIUM,
    ChangeCategory.LOGIC: ModelTier.STANDARD,
    ChangeCategory.API: ModelTier.STANDARD,
    ChangeCategory.PERFORMANCE: ModelTier.STANDARD,
    ChangeCategory.REFACTOR: ModelTier.FAST,
    ChangeCategory.STYLE: ModelTier.FAST,
    ChangeCategory.DOCUMENTATION: ModelTier.FAST,
    ChangeCategory.TESTS: ModelTier.STANDARD,
    ChangeCategory.DEPENDENCY: ModelTier.STANDARD,
    ChangeCategory.CONFIG: ModelTier.FAST,
}


# ── Data classes ─────────────────────────────────────────────────────────

@dataclass
class ModelProfile:
    """Capabilities and cost profile of a model."""

    model_id: str
    tier: ModelTier
    capabilities: list[ChangeCategory]
    cost_per_1k_tokens: float
    avg_latency_ms: int
    quality_score: float  # 0-1, historical quality
    max_context_tokens: int = 128_000
    active: bool = True


@dataclass
class ChangeAnalysis:
    """Analysis of a code change for routing purposes."""

    diff_id: str
    categories: list[ChangeCategory]
    primary_category: ChangeCategory
    complexity_score: float  # 0-1
    line_count: int
    file_count: int
    recommended_depth: ReviewDepth
    recommended_tier: ModelTier


@dataclass
class RoutingDecision:
    """Routing decision for a code review task."""

    diff_id: str
    model_id: str
    model_tier: ModelTier
    review_depth: ReviewDepth
    change_categories: list[ChangeCategory]
    estimated_cost: float
    rationale: str
    routed_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
    )


@dataclass
class ReviewFinding:
    """A single finding from a model review."""

    id: str
    model_id: str
    category: ChangeCategory
    severity: str
    message: str
    file_path: str = ""
    line: int | None = None
    actionable: bool = True


@dataclass
class AggregatedReview:
    """Aggregated review from multiple model outputs."""

    diff_id: str
    findings: list[ReviewFinding]
    models_used: list[str]
    total_cost: float
    gate_decision: GateDecision
    coverage: dict[str, bool] = field(default_factory=dict)


@dataclass
class RoutingAnalytics:
    """Analytics about routing decisions."""

    total_reviews: int
    reviews_by_tier: dict[str, int]
    reviews_by_category: dict[str, int]
    avg_cost: float
    avg_findings: float


# ── Main class ──────────────────────────────────────────────────────────

class MultiModelReviewRouter:
    """Route code review tasks to appropriate models based on change analysis.

    Uses change classification, complexity estimation, and model capabilities
    to make cost-effective routing decisions.
    """

    __test__ = False

    def __init__(
        self,
        models: list[ModelProfile] | None = None,
        cost_weight: float = 0.3,
        quality_weight: float = 0.7,
        gate_block_findings: int = 5,
        gate_warn_findings: int = 2,
    ) -> None:
        self.models: dict[str, ModelProfile] = {}
        if models:
            for m in models:
                self.models[m.model_id] = m
        self.cost_weight = cost_weight
        self.quality_weight = quality_weight
        self.gate_block_findings = gate_block_findings
        self.gate_warn_findings = gate_warn_findings
        self._decisions: list[RoutingDecision] = []

    def register_model(self, profile: ModelProfile) -> None:
        """Register a model profile."""
        self.models[profile.model_id] = profile

    # ── Change classification ────────────────────────────────────────────

    def classify_change(
        self,
        diff_id: str,
        diff_text: str,
        file_paths: list[str] | None = None,
    ) -> ChangeAnalysis:
        """Classify a code change for routing."""
        categories = self._detect_categories(diff_text, file_paths or [])
        if not categories:
            categories = [ChangeCategory.LOGIC]

        primary = categories[0]
        complexity = self._estimate_complexity(diff_text)
        lines = len(diff_text.strip().splitlines())
        files = len(file_paths) if file_paths else 1

        # Determine review depth
        if complexity > 0.7 or primary == ChangeCategory.SECURITY:
            depth = ReviewDepth.DEEP
        elif complexity > 0.3:
            depth = ReviewDepth.STANDARD
        else:
            depth = ReviewDepth.SHALLOW

        # Determine minimum tier
        tier = _MIN_TIER.get(primary, ModelTier.STANDARD)
        if complexity > 0.7 and tier == ModelTier.FAST:
            tier = ModelTier.STANDARD

        return ChangeAnalysis(
            diff_id=diff_id,
            categories=categories,
            primary_category=primary,
            complexity_score=round(complexity, 4),
            line_count=lines,
            file_count=files,
            recommended_depth=depth,
            recommended_tier=tier,
        )

    def _detect_categories(
        self,
        diff_text: str,
        file_paths: list[str],
    ) -> list[ChangeCategory]:
        """Detect change categories from diff content and file paths."""
        text_lower = diff_text.lower()
        paths_lower = " ".join(file_paths).lower()
        combined = text_lower + " " + paths_lower

        scores: dict[ChangeCategory, int] = {}
        for cat, keywords in _CATEGORY_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in combined)
            if score > 0:
                scores[cat] = score

        # Sort by score descending
        sorted_cats = sorted(scores.keys(), key=lambda c: scores[c], reverse=True)
        return sorted_cats[:3] if sorted_cats else [ChangeCategory.LOGIC]

    def _estimate_complexity(self, diff_text: str) -> float:
        """Estimate diff complexity (0-1)."""
        lines = diff_text.strip().splitlines()
        if not lines:
            return 0.0

        change_lines = [ln for ln in lines if ln.startswith("+") or ln.startswith("-")]
        ratio = len(change_lines) / max(len(lines), 1)

        # Bonus complexity for certain patterns
        complexity = ratio
        if len(change_lines) > 100:
            complexity = min(complexity + 0.2, 1.0)
        if re.search(r"(?:class|def|function|async)\s+\w+", diff_text):
            complexity = min(complexity + 0.1, 1.0)
        if re.search(r"(?:try|except|catch|throw|raise)\s", diff_text):
            complexity = min(complexity + 0.1, 1.0)

        return min(complexity, 1.0)

    # ── Routing ──────────────────────────────────────────────────────────

    def route(self, analysis: ChangeAnalysis) -> RoutingDecision:
        """Route a change to the best model."""
        if not self.models:
            return RoutingDecision(
                diff_id=analysis.diff_id,
                model_id="none",
                model_tier=ModelTier.STANDARD,
                review_depth=analysis.recommended_depth,
                change_categories=analysis.categories,
                estimated_cost=0.0,
                rationale="No models registered",
            )

        candidates = self._filter_candidates(analysis)
        if not candidates:
            # Fallback to any active model
            candidates = [m for m in self.models.values() if m.active]

        if not candidates:
            return RoutingDecision(
                diff_id=analysis.diff_id,
                model_id="none",
                model_tier=ModelTier.STANDARD,
                review_depth=analysis.recommended_depth,
                change_categories=analysis.categories,
                estimated_cost=0.0,
                rationale="No active models available",
            )

        # Score candidates
        best = self._score_and_select(candidates, analysis)

        # Estimate cost
        est_tokens = analysis.line_count * 10  # rough estimate
        est_cost = (est_tokens / 1000) * best.cost_per_1k_tokens

        decision = RoutingDecision(
            diff_id=analysis.diff_id,
            model_id=best.model_id,
            model_tier=best.tier,
            review_depth=analysis.recommended_depth,
            change_categories=analysis.categories,
            estimated_cost=round(est_cost, 4),
            rationale=(
                f"Selected {best.model_id} (tier={best.tier}, "
                f"quality={best.quality_score}) for {analysis.primary_category} change"
            ),
        )

        self._decisions.append(decision)
        return decision

    def _filter_candidates(self, analysis: ChangeAnalysis) -> list[ModelProfile]:
        """Filter models that meet minimum tier and capability."""
        tier_order = [ModelTier.FAST, ModelTier.STANDARD, ModelTier.PREMIUM]
        min_idx = tier_order.index(analysis.recommended_tier)

        candidates = []
        for m in self.models.values():
            if not m.active:
                continue
            if tier_order.index(m.tier) < min_idx:
                continue
            # Check if model has relevant capability
            if any(c in m.capabilities for c in analysis.categories):
                candidates.append(m)

        return candidates

    def _score_and_select(
        self,
        candidates: list[ModelProfile],
        analysis: ChangeAnalysis,
    ) -> ModelProfile:
        """Score candidates and select the best."""
        def score(m: ModelProfile) -> float:
            quality = m.quality_score * self.quality_weight
            # Invert cost: lower cost → higher score
            max_cost = max(c.cost_per_1k_tokens for c in candidates)
            cost_score = (1.0 - m.cost_per_1k_tokens / max(max_cost, 0.001)) * self.cost_weight
            # Capability match bonus
            cap_match = sum(1 for c in analysis.categories if c in m.capabilities)
            cap_bonus = cap_match * 0.1
            return quality + cost_score + cap_bonus

        return max(candidates, key=score)

    # ── Review aggregation ───────────────────────────────────────────────

    def aggregate_reviews(
        self,
        diff_id: str,
        model_findings: list[tuple[str, list[ReviewFinding], float]],
    ) -> AggregatedReview:
        """Aggregate findings from multiple model reviews.

        Each tuple is (model_id, findings, cost).
        """
        all_findings: list[ReviewFinding] = []
        models_used: list[str] = []
        total_cost = 0.0

        for model_id, findings, cost in model_findings:
            all_findings.extend(findings)
            models_used.append(model_id)
            total_cost += cost

        # Deduplicate by message similarity
        deduped = self._deduplicate_findings(all_findings)

        # Gate decision
        critical_high = sum(
            1 for f in deduped if f.severity in ("critical", "high")
        )
        if critical_high >= self.gate_block_findings:
            gate = GateDecision.BLOCK
        elif len(deduped) >= self.gate_warn_findings:
            gate = GateDecision.WARN
        else:
            gate = GateDecision.PASS

        # Coverage: which categories had findings
        coverage = {c.value: False for c in ChangeCategory}
        for f in deduped:
            coverage[f.category.value] = True

        return AggregatedReview(
            diff_id=diff_id,
            findings=deduped,
            models_used=models_used,
            total_cost=round(total_cost, 4),
            gate_decision=gate,
            coverage=coverage,
        )

    def _deduplicate_findings(
        self,
        findings: list[ReviewFinding],
    ) -> list[ReviewFinding]:
        """Remove duplicate findings based on message similarity."""
        seen_messages: set[str] = set()
        unique: list[ReviewFinding] = []

        for f in findings:
            # Normalize message for comparison
            norm = f.message.lower().strip()
            if norm not in seen_messages:
                seen_messages.add(norm)
                unique.append(f)

        return unique

    # ── Analytics ────────────────────────────────────────────────────────

    def get_analytics(self) -> RoutingAnalytics:
        """Get routing analytics."""
        if not self._decisions:
            return RoutingAnalytics(
                total_reviews=0,
                reviews_by_tier={},
                reviews_by_category={},
                avg_cost=0.0,
                avg_findings=0.0,
            )

        by_tier: dict[str, int] = {}
        by_cat: dict[str, int] = {}
        total_cost = 0.0

        for d in self._decisions:
            by_tier[d.model_tier] = by_tier.get(d.model_tier, 0) + 1
            for c in d.change_categories:
                by_cat[c] = by_cat.get(c, 0) + 1
            total_cost += d.estimated_cost

        return RoutingAnalytics(
            total_reviews=len(self._decisions),
            reviews_by_tier=by_tier,
            reviews_by_category=by_cat,
            avg_cost=round(total_cost / len(self._decisions), 4),
            avg_findings=0.0,  # Would need review results to compute
        )

    @property
    def decisions(self) -> list[RoutingDecision]:
        return list(self._decisions)
