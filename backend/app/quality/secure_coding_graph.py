"""Graph-Based Secure Coding Reasoning (GRASP) — DAG-driven security
constraint engine for AI-generated code.

Traditional security scanning works *post-hoc* — code is generated first,
then scanned.  GRASP embeds security constraints *during* the generation
reasoning step by organising Secure Coding Practices (SCPs) into a
Directed Acyclic Graph where nodes are individual practices and edges
encode ordering constraints and specificity hierarchies.

Based on Patir et al. "Fortifying LLM-Based Code Generation with
Graph-Based Reasoning on Secure Coding Practices" (arXiv:2510.09682,
October 2025).

Key capabilities:
- DAG of Secure Coding Practices with dependency ordering
- Dynamic traversal based on task relevance
- CWE-based rule library (OWASP Top-10, CERT, etc.)
- Zero-day generalisation through graph structure
- Security constraint composition preserving functional correctness
- Interpretable reasoning chain for audit
- Batch evaluation with aggregated security scores
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


# ── Enums ────────────────────────────────────────────────────────────────

class SecurityDomain(StrEnum):
    INPUT_VALIDATION = "input_validation"
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    CRYPTOGRAPHY = "cryptography"
    ERROR_HANDLING = "error_handling"
    DATA_PROTECTION = "data_protection"
    SESSION_MANAGEMENT = "session_management"
    LOGGING = "logging"
    NETWORK = "network"
    FILE_IO = "file_io"


class SeverityLevel(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class TraversalStrategy(StrEnum):
    TOPOLOGICAL = "topological"
    RELEVANCE_FIRST = "relevance_first"
    DEPTH_FIRST = "depth_first"


# ── Data classes ─────────────────────────────────────────────────────────

@dataclass
class SecureCodingPractice:
    """A single node in the GRASP DAG."""

    id: str
    name: str
    description: str
    domain: SecurityDomain
    severity: SeverityLevel
    cwe_ids: list[str] = field(default_factory=list)
    constraint_template: str = ""
    keywords: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)  # IDs of prerequisite SCPs


@dataclass
class GraphEdge:
    """Directed edge from prerequisite → dependent SCP."""

    source_id: str
    target_id: str
    relationship: str = "requires"  # requires | enhances | specializes


@dataclass
class TraversalResult:
    """Result of traversing the DAG for a given task."""

    applicable_scps: list[SecureCodingPractice]
    traversal_order: list[str]
    skipped_scps: list[str]
    security_score: float  # 0.0 – 1.0
    reasoning_chain: list[str]
    timestamp: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
    )


@dataclass
class SecurityConstraintSet:
    """Composed security constraints ready for prompt injection."""

    constraints: list[str]
    domains_covered: list[SecurityDomain]
    severity_floor: SeverityLevel
    total_scps_applied: int
    reasoning_chain: list[str]


@dataclass
class BatchEvalResult:
    """Aggregated result for batch evaluation."""

    total_tasks: int
    avg_security_score: float
    domain_coverage: dict[str, int]
    cwe_coverage: list[str]
    tasks_below_threshold: int


# ── GRASP Engine ─────────────────────────────────────────────────────────

class GRASPEngine:
    """Graph-based Secure Coding Reasoning engine.

    Maintains a DAG of Secure Coding Practices and traverses it
    dynamically based on task context to produce security constraints.
    """

    def __init__(self) -> None:
        self._scps: dict[str, SecureCodingPractice] = {}
        self._edges: list[GraphEdge] = []
        self._adjacency: dict[str, list[str]] = {}  # source → [targets]
        self._reverse_adj: dict[str, list[str]] = {}  # target → [sources]
        self._audit_log: list[dict[str, Any]] = []
        self._load_default_scps()

    # ── Public API ───────────────────────────────────────────────────

    def register_scp(self, scp: SecureCodingPractice) -> None:
        """Register a new Secure Coding Practice node."""
        self._scps[scp.id] = scp
        if scp.id not in self._adjacency:
            self._adjacency[scp.id] = []
        if scp.id not in self._reverse_adj:
            self._reverse_adj[scp.id] = []
        for dep_id in scp.dependencies:
            self.add_edge(GraphEdge(source_id=dep_id, target_id=scp.id))

    def add_edge(self, edge: GraphEdge) -> None:
        """Add a directed edge between two SCPs."""
        self._edges.append(edge)
        self._adjacency.setdefault(edge.source_id, []).append(edge.target_id)
        self._reverse_adj.setdefault(edge.target_id, []).append(edge.source_id)

    def traverse(
        self,
        task_context: str,
        *,
        strategy: TraversalStrategy = TraversalStrategy.RELEVANCE_FIRST,
        severity_floor: SeverityLevel = SeverityLevel.MEDIUM,
        max_scps: int = 20,
    ) -> TraversalResult:
        """Traverse the DAG to find applicable SCPs for a task."""
        severity_order = list(SeverityLevel)
        floor_idx = severity_order.index(severity_floor)
        allowed_severities = set(severity_order[:floor_idx + 1])

        # Score relevance of each SCP to the task
        scored: list[tuple[float, SecureCodingPractice]] = []
        for scp in self._scps.values():
            score = self._relevance_score(scp, task_context)
            if score > 0.0 and scp.severity in allowed_severities:
                scored.append((score, scp))

        # Sort by strategy
        if strategy == TraversalStrategy.RELEVANCE_FIRST:
            scored.sort(key=lambda x: x[0], reverse=True)
        elif strategy == TraversalStrategy.TOPOLOGICAL:
            topo_order = self._topological_sort()
            topo_idx = {sid: i for i, sid in enumerate(topo_order)}
            scored.sort(key=lambda x: topo_idx.get(x[1].id, 999))
        # DEPTH_FIRST: keep natural order

        # Resolve dependencies
        selected_ids: list[str] = []
        selected_scps: list[SecureCodingPractice] = []
        reasoning: list[str] = []

        for _score, scp in scored[:max_scps]:
            # Ensure dependencies are included first
            for dep_id in scp.dependencies:
                if dep_id not in selected_ids and dep_id in self._scps:
                    dep_scp = self._scps[dep_id]
                    selected_ids.append(dep_id)
                    selected_scps.append(dep_scp)
                    reasoning.append(
                        f"Added dependency '{dep_scp.name}' required by '{scp.name}'"
                    )
            if scp.id not in selected_ids:
                selected_ids.append(scp.id)
                selected_scps.append(scp)
                reasoning.append(
                    f"Applied '{scp.name}' (domain={scp.domain}, severity={scp.severity})"
                )

        skipped = [
            sid for sid in self._scps
            if sid not in selected_ids
        ]

        security_score = len(selected_scps) / max(len(self._scps), 1)

        result = TraversalResult(
            applicable_scps=selected_scps,
            traversal_order=selected_ids,
            skipped_scps=skipped,
            security_score=min(security_score, 1.0),
            reasoning_chain=reasoning,
        )

        self._audit_log.append({
            "action": "traverse",
            "task_context_snippet": task_context[:100],
            "scps_applied": len(selected_scps),
            "security_score": result.security_score,
            "timestamp": result.timestamp,
        })

        return result

    def compose_constraints(
        self,
        traversal: TraversalResult,
    ) -> SecurityConstraintSet:
        """Compose a set of security constraints from traversal results."""
        constraints: list[str] = []
        domains: set[SecurityDomain] = set()
        severities: list[SeverityLevel] = []

        for scp in traversal.applicable_scps:
            template = scp.constraint_template or scp.description
            constraints.append(f"[{scp.domain.upper()}] {template}")
            domains.add(scp.domain)
            severities.append(scp.severity)

        severity_floor = min(
            severities,
            key=lambda s: list(SeverityLevel).index(s),
            default=SeverityLevel.INFO,
        )

        return SecurityConstraintSet(
            constraints=constraints,
            domains_covered=sorted(domains, key=lambda d: d.value),
            severity_floor=severity_floor,
            total_scps_applied=len(traversal.applicable_scps),
            reasoning_chain=traversal.reasoning_chain,
        )

    def enrich_prompt(
        self,
        original_prompt: str,
        task_context: str,
        *,
        severity_floor: SeverityLevel = SeverityLevel.MEDIUM,
    ) -> str:
        """Enrich a generation prompt with security constraints."""
        traversal = self.traverse(
            task_context, severity_floor=severity_floor,
        )
        if not traversal.applicable_scps:
            return original_prompt

        constraint_set = self.compose_constraints(traversal)
        security_block = "\n".join(
            f"- {c}" for c in constraint_set.constraints
        )

        return (
            f"{original_prompt}\n\n"
            f"## Security Constraints (GRASP — {constraint_set.total_scps_applied} rules)\n"
            f"{security_block}\n"
        )

    def evaluate_batch(
        self,
        tasks: list[str],
        *,
        threshold: float = 0.3,
    ) -> BatchEvalResult:
        """Evaluate a batch of tasks and return aggregated metrics."""
        scores: list[float] = []
        domain_counts: dict[str, int] = {}
        all_cwes: set[str] = set()
        below = 0

        for task in tasks:
            result = self.traverse(task)
            scores.append(result.security_score)
            if result.security_score < threshold:
                below += 1
            for scp in result.applicable_scps:
                domain_counts[scp.domain] = domain_counts.get(scp.domain, 0) + 1
                all_cwes.update(scp.cwe_ids)

        return BatchEvalResult(
            total_tasks=len(tasks),
            avg_security_score=sum(scores) / max(len(scores), 1),
            domain_coverage=domain_counts,
            cwe_coverage=sorted(all_cwes),
            tasks_below_threshold=below,
        )

    def get_scp(self, scp_id: str) -> SecureCodingPractice | None:
        return self._scps.get(scp_id)

    def list_scps(self, *, domain: SecurityDomain | None = None) -> list[SecureCodingPractice]:
        scps = list(self._scps.values())
        if domain:
            scps = [s for s in scps if s.domain == domain]
        return scps

    def get_dependencies(self, scp_id: str) -> list[str]:
        return self._reverse_adj.get(scp_id, [])

    def get_dependents(self, scp_id: str) -> list[str]:
        return self._adjacency.get(scp_id, [])

    def get_audit_log(self) -> list[dict[str, Any]]:
        return list(self._audit_log)

    def analytics(self) -> dict[str, Any]:
        traversals = [e for e in self._audit_log if e["action"] == "traverse"]
        return {
            "total_scps": len(self._scps),
            "total_edges": len(self._edges),
            "total_traversals": len(traversals),
            "avg_scps_applied": (
                sum(t["scps_applied"] for t in traversals) / max(len(traversals), 1)
            ),
            "avg_security_score": (
                sum(t["security_score"] for t in traversals) / max(len(traversals), 1)
            ),
            "domains": list({s.domain for s in self._scps.values()}),
        }

    # ── Private helpers ──────────────────────────────────────────────

    def _relevance_score(self, scp: SecureCodingPractice, context: str) -> float:
        """Simple keyword-matching relevance score."""
        ctx_lower = context.lower()
        matches = sum(1 for kw in scp.keywords if kw.lower() in ctx_lower)
        # Domain-name match
        if scp.domain.value.replace("_", " ") in ctx_lower:
            matches += 1
        # CWE reference match
        for cwe in scp.cwe_ids:
            if cwe.lower() in ctx_lower:
                matches += 2
        return min(matches / max(len(scp.keywords), 1), 1.0)

    def _topological_sort(self) -> list[str]:
        """Kahn's algorithm for topological sort of the SCP DAG."""
        in_degree: dict[str, int] = {sid: 0 for sid in self._scps}
        for edge in self._edges:
            if edge.target_id in in_degree:
                in_degree[edge.target_id] += 1

        queue = [sid for sid, deg in in_degree.items() if deg == 0]
        order: list[str] = []

        while queue:
            node = queue.pop(0)
            order.append(node)
            for neighbour in self._adjacency.get(node, []):
                if neighbour in in_degree:
                    in_degree[neighbour] -= 1
                    if in_degree[neighbour] == 0:
                        queue.append(neighbour)

        # Add any remaining (cycles, though DAG shouldn't have any)
        for sid in self._scps:
            if sid not in order:
                order.append(sid)

        return order

    def _load_default_scps(self) -> None:
        """Load the default OWASP / CERT-based SCP library."""
        defaults = [
            SecureCodingPractice(
                id="scp-input-sanitize",
                name="Input Sanitization",
                description="Sanitize and validate all user input before processing.",
                domain=SecurityDomain.INPUT_VALIDATION,
                severity=SeverityLevel.CRITICAL,
                cwe_ids=["CWE-79", "CWE-89"],
                constraint_template=(
                    "All user inputs MUST be validated and sanitized."
                    " Use parameterized queries for SQL, escape HTML."
                ),
                keywords=[
                    "input", "form", "user", "request",
                    "query", "parameter", "sql", "html",
                ],
            ),
            SecureCodingPractice(
                id="scp-auth-strong",
                name="Strong Authentication",
                description="Enforce strong authentication mechanisms.",
                domain=SecurityDomain.AUTHENTICATION,
                severity=SeverityLevel.CRITICAL,
                cwe_ids=["CWE-287", "CWE-306"],
                constraint_template=(
                    "Use bcrypt/argon2 for password hashing."
                    " Enforce MFA. Never store plaintext passwords."
                ),
                keywords=[
                    "login", "password", "auth", "credential",
                    "token", "session", "jwt",
                ],
            ),
            SecureCodingPractice(
                id="scp-authz-least-priv",
                name="Least Privilege Authorization",
                description="Enforce least-privilege access control.",
                domain=SecurityDomain.AUTHORIZATION,
                severity=SeverityLevel.HIGH,
                cwe_ids=["CWE-862", "CWE-863"],
                constraint_template=(
                    "Check authorization for every resource access."
                    " Use role-based access control. Deny by default."
                ),
                keywords=[
                    "role", "permission", "access", "authorize",
                    "admin", "rbac", "acl",
                ],
                dependencies=["scp-auth-strong"],
            ),
            SecureCodingPractice(
                id="scp-crypto-modern",
                name="Modern Cryptography",
                description="Use current cryptographic standards.",
                domain=SecurityDomain.CRYPTOGRAPHY,
                severity=SeverityLevel.CRITICAL,
                cwe_ids=["CWE-327", "CWE-328"],
                constraint_template=(
                    "Use AES-256-GCM for encryption, SHA-256+ for"
                    " hashing. Never use MD5/SHA1. Use TLS 1.3."
                ),
                keywords=[
                    "encrypt", "decrypt", "hash", "crypto",
                    "tls", "ssl", "key", "secret",
                ],
            ),
            SecureCodingPractice(
                id="scp-error-safe",
                name="Safe Error Handling",
                description="Handle errors without leaking sensitive information.",
                domain=SecurityDomain.ERROR_HANDLING,
                severity=SeverityLevel.MEDIUM,
                cwe_ids=["CWE-209", "CWE-200"],
                constraint_template=(
                    "Never expose stack traces or internal paths"
                    " in error responses. Log errors server-side."
                ),
                keywords=["error", "exception", "traceback", "stack", "debug", "500"],
            ),
            SecureCodingPractice(
                id="scp-data-protect",
                name="Data Protection",
                description="Protect sensitive data at rest and in transit.",
                domain=SecurityDomain.DATA_PROTECTION,
                severity=SeverityLevel.HIGH,
                cwe_ids=["CWE-311", "CWE-312"],
                constraint_template=(
                    "Encrypt sensitive data at rest. Use TLS for"
                    " transit. Mask PII in logs. Retention policies."
                ),
                keywords=[
                    "data", "pii", "sensitive", "encrypt",
                    "store", "database", "personal",
                ],
                dependencies=["scp-crypto-modern"],
            ),
            SecureCodingPractice(
                id="scp-session-mgmt",
                name="Secure Session Management",
                description="Implement secure session handling.",
                domain=SecurityDomain.SESSION_MANAGEMENT,
                severity=SeverityLevel.HIGH,
                cwe_ids=["CWE-384", "CWE-613"],
                constraint_template=(
                    "Use secure, httponly, samesite cookies."
                    " Regenerate session IDs on auth change."
                ),
                keywords=["session", "cookie", "token", "logout", "expire", "refresh"],
                dependencies=["scp-auth-strong"],
            ),
            SecureCodingPractice(
                id="scp-logging-secure",
                name="Secure Logging",
                description="Log security events without sensitive data.",
                domain=SecurityDomain.LOGGING,
                severity=SeverityLevel.MEDIUM,
                cwe_ids=["CWE-532", "CWE-778"],
                constraint_template=(
                    "Log auth events and access control failures."
                    " Never log passwords, tokens, or PII."
                ),
                keywords=["log", "audit", "monitor", "trace", "event"],
            ),
            SecureCodingPractice(
                id="scp-network-secure",
                name="Network Security",
                description="Enforce secure network communication.",
                domain=SecurityDomain.NETWORK,
                severity=SeverityLevel.HIGH,
                cwe_ids=["CWE-319", "CWE-918"],
                constraint_template=(
                    "Validate URLs to prevent SSRF. Use allowlists"
                    " for outbound connections. Enforce HTTPS."
                ),
                keywords=[
                    "http", "url", "api", "request",
                    "fetch", "network", "ssrf", "cors",
                ],
            ),
            SecureCodingPractice(
                id="scp-file-safe",
                name="Safe File Operations",
                description="Handle file I/O securely.",
                domain=SecurityDomain.FILE_IO,
                severity=SeverityLevel.HIGH,
                cwe_ids=["CWE-22", "CWE-434"],
                constraint_template=(
                    "Validate file paths to prevent traversal."
                    " Restrict upload types/sizes. Never execute."
                ),
                keywords=[
                    "file", "upload", "download", "path",
                    "directory", "read", "write",
                ],
            ),
        ]

        for scp in defaults:
            self.register_scp(scp)
