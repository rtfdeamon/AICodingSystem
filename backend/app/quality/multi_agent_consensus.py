"""Multi-Agent Consensus Protocol -- aggregate decisions from multiple AI agents.

When critical decisions (code review verdicts, security assessments, deployment
approvals) benefit from diverse perspectives, this module orchestrates parallel
agent invocations, collects individual votes, and applies configurable consensus
strategies to reach a final decision.

Key features:
- Multiple voting strategies: unanimous, majority, weighted, quorum
- Agent diversity scoring (different models/prompts → higher diversity)
- Conflict resolution with escalation to human reviewer
- Confidence-weighted voting (low-confidence votes count less)
- Dissent tracking and minority opinion preservation
- Round-based deliberation with opinion revision
- Consensus analytics: agreement rate, decision latency, flip tracking
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


# ── Enums ────────────────────────────────────────────────────────────────

class VotingStrategy(StrEnum):
    UNANIMOUS = "unanimous"
    MAJORITY = "majority"
    SUPERMAJORITY = "supermajority"  # 2/3
    WEIGHTED = "weighted"
    QUORUM = "quorum"


class Vote(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"
    ABSTAIN = "abstain"
    NEEDS_DISCUSSION = "needs_discussion"


class ConsensusOutcome(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"
    NO_CONSENSUS = "no_consensus"
    ESCALATED = "escalated"
    PENDING = "pending"


class AgentRole(StrEnum):
    REVIEWER = "reviewer"
    SECURITY_AUDITOR = "security_auditor"
    ARCHITECT = "architect"
    TESTING_EXPERT = "testing_expert"
    PERFORMANCE_ANALYST = "performance_analyst"


# ── Dataclasses ──────────────────────────────────────────────────────────

@dataclass
class AgentVoter:
    """An AI agent participating in consensus."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    role: AgentRole = AgentRole.REVIEWER
    model: str = ""  # e.g. "claude-sonnet-4-6", "gpt-4o"
    weight: float = 1.0  # for weighted voting
    expertise_areas: list[str] = field(default_factory=list)


@dataclass
class AgentBallot:
    """A single agent's vote on a decision."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    agent_id: str = ""
    vote: Vote = Vote.APPROVE
    confidence: float = 0.8  # 0-1
    reasoning: str = ""
    findings: list[str] = field(default_factory=list)
    round_number: int = 1
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    revised_from: Vote | None = None  # if opinion changed


@dataclass
class ConsensusDecision:
    """The final decision from a consensus round."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    topic: str = ""
    outcome: ConsensusOutcome = ConsensusOutcome.PENDING
    strategy: VotingStrategy = VotingStrategy.MAJORITY
    ballots: list[AgentBallot] = field(default_factory=list)
    rounds_needed: int = 1
    dissenting_opinions: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    decided_at: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DeliberationRound:
    """A single round of deliberation."""
    round_number: int = 1
    ballots: list[AgentBallot] = field(default_factory=list)
    opinion_changes: int = 0
    agreement_score: float = 0.0  # 0-1


# ── Consensus Protocol ───────────────────────────────────────────────────

class MultiAgentConsensus:
    """Orchestrates multi-agent consensus decisions."""

    def __init__(
        self,
        strategy: VotingStrategy = VotingStrategy.MAJORITY,
        max_rounds: int = 3,
        quorum_threshold: float = 0.6,
        confidence_threshold: float = 0.5,
        enable_deliberation: bool = True,
    ):
        self.strategy = strategy
        self.max_rounds = max_rounds
        self.quorum_threshold = quorum_threshold
        self.confidence_threshold = confidence_threshold
        self.enable_deliberation = enable_deliberation
        self._voters: dict[str, AgentVoter] = {}
        self._decisions: list[ConsensusDecision] = []

    # ── Voter Management ──────────────────────────────────────────────

    def register_voter(
        self, name: str, role: AgentRole = AgentRole.REVIEWER,
        model: str = "", weight: float = 1.0,
        expertise_areas: list[str] | None = None,
    ) -> AgentVoter:
        """Register an agent as a voter."""
        voter = AgentVoter(
            name=name, role=role, model=model, weight=weight,
            expertise_areas=expertise_areas or [],
        )
        self._voters[voter.id] = voter
        logger.info("Registered voter %s (%s, model=%s)", name, role, model)
        return voter

    def get_voter(self, voter_id: str) -> AgentVoter | None:
        return self._voters.get(voter_id)

    def list_voters(self) -> list[AgentVoter]:
        return list(self._voters.values())

    # ── Voting ────────────────────────────────────────────────────────

    def cast_vote(
        self, agent_id: str, vote: Vote, confidence: float = 0.8,
        reasoning: str = "", findings: list[str] | None = None,
        round_number: int = 1,
    ) -> AgentBallot:
        """Cast a vote from an agent."""
        if agent_id not in self._voters:
            raise ValueError(f"Agent {agent_id} not registered as a voter")

        ballot = AgentBallot(
            agent_id=agent_id,
            vote=vote,
            confidence=max(0.0, min(1.0, confidence)),
            reasoning=reasoning,
            findings=findings or [],
            round_number=round_number,
        )
        return ballot

    # ── Decision Making ───────────────────────────────────────────────

    def decide(
        self, topic: str, ballots: list[AgentBallot],
        strategy: VotingStrategy | None = None,
    ) -> ConsensusDecision:
        """Evaluate ballots and reach a consensus decision."""
        effective_strategy = strategy or self.strategy

        decision = ConsensusDecision(
            topic=topic,
            strategy=effective_strategy,
            ballots=ballots,
        )

        # Filter low-confidence votes
        effective_ballots = [
            b for b in ballots
            if b.confidence >= self.confidence_threshold and b.vote != Vote.ABSTAIN
        ]

        if not effective_ballots:
            decision.outcome = ConsensusOutcome.NO_CONSENSUS
            decision.decided_at = datetime.now(UTC).isoformat()
            self._decisions.append(decision)
            return decision

        # Count votes
        approve_count = sum(1 for b in effective_ballots if b.vote == Vote.APPROVE)
        reject_count = sum(1 for b in effective_ballots if b.vote == Vote.REJECT)
        discuss_count = sum(1 for b in effective_ballots if b.vote == Vote.NEEDS_DISCUSSION)
        total_effective = len(effective_ballots)

        # Apply strategy
        outcome = self._apply_strategy(
            effective_strategy, approve_count, reject_count,
            discuss_count, total_effective, effective_ballots,
        )

        decision.outcome = outcome

        # Collect dissenting opinions
        if outcome == ConsensusOutcome.APPROVED:
            decision.dissenting_opinions = [
                b.reasoning for b in effective_ballots
                if b.vote == Vote.REJECT and b.reasoning
            ]
        elif outcome == ConsensusOutcome.REJECTED:
            decision.dissenting_opinions = [
                b.reasoning for b in effective_ballots
                if b.vote == Vote.APPROVE and b.reasoning
            ]

        decision.decided_at = datetime.now(UTC).isoformat()
        self._decisions.append(decision)
        return decision

    def _apply_strategy(
        self, strategy: VotingStrategy, approve: int, reject: int,
        discuss: int, total: int, ballots: list[AgentBallot],
    ) -> ConsensusOutcome:
        if discuss > total / 2:
            return ConsensusOutcome.ESCALATED

        if strategy == VotingStrategy.UNANIMOUS:
            if approve == total:
                return ConsensusOutcome.APPROVED
            if reject == total:
                return ConsensusOutcome.REJECTED
            return ConsensusOutcome.NO_CONSENSUS

        if strategy == VotingStrategy.MAJORITY:
            if approve > total / 2:
                return ConsensusOutcome.APPROVED
            if reject > total / 2:
                return ConsensusOutcome.REJECTED
            return ConsensusOutcome.NO_CONSENSUS

        if strategy == VotingStrategy.SUPERMAJORITY:
            if approve >= total * 2 / 3:
                return ConsensusOutcome.APPROVED
            if reject >= total * 2 / 3:
                return ConsensusOutcome.REJECTED
            return ConsensusOutcome.NO_CONSENSUS

        if strategy == VotingStrategy.WEIGHTED:
            return self._weighted_decision(ballots)

        if strategy == VotingStrategy.QUORUM:
            if total < len(self._voters) * self.quorum_threshold:
                return ConsensusOutcome.NO_CONSENSUS
            if approve > total / 2:
                return ConsensusOutcome.APPROVED
            if reject > total / 2:
                return ConsensusOutcome.REJECTED
            return ConsensusOutcome.NO_CONSENSUS

        return ConsensusOutcome.NO_CONSENSUS

    def _weighted_decision(self, ballots: list[AgentBallot]) -> ConsensusOutcome:
        """Compute weighted vote totals."""
        approve_weight = 0.0
        reject_weight = 0.0

        for ballot in ballots:
            voter = self._voters.get(ballot.agent_id)
            weight = (voter.weight if voter else 1.0) * ballot.confidence
            if ballot.vote == Vote.APPROVE:
                approve_weight += weight
            elif ballot.vote == Vote.REJECT:
                reject_weight += weight

        total_weight = approve_weight + reject_weight
        if total_weight == 0:
            return ConsensusOutcome.NO_CONSENSUS

        if approve_weight / total_weight > 0.6:
            return ConsensusOutcome.APPROVED
        if reject_weight / total_weight > 0.6:
            return ConsensusOutcome.REJECTED
        return ConsensusOutcome.NO_CONSENSUS

    # ── Deliberation ──────────────────────────────────────────────────

    def run_deliberation(
        self, topic: str, rounds: list[list[AgentBallot]],
    ) -> ConsensusDecision:
        """Run multi-round deliberation with opinion revision tracking."""
        if not rounds:
            raise ValueError("At least one round of ballots required")

        all_ballots: list[AgentBallot] = []
        deliberation_rounds: list[DeliberationRound] = []
        previous_votes: dict[str, Vote] = {}

        for round_num, round_ballots in enumerate(rounds, 1):
            opinion_changes = 0
            for ballot in round_ballots:
                ballot.round_number = round_num
                if (ballot.agent_id in previous_votes
                        and ballot.vote != previous_votes[ballot.agent_id]):
                    ballot.revised_from = previous_votes[ballot.agent_id]
                    opinion_changes += 1
                previous_votes[ballot.agent_id] = ballot.vote

            agreement = self._agreement_score(round_ballots)
            delib_round = DeliberationRound(
                round_number=round_num,
                ballots=round_ballots,
                opinion_changes=opinion_changes,
                agreement_score=agreement,
            )
            deliberation_rounds.append(delib_round)
            all_ballots.extend(round_ballots)

        # Use final round for decision
        final_ballots = rounds[-1]
        decision = self.decide(topic, final_ballots)
        decision.rounds_needed = len(rounds)
        decision.ballots = all_ballots
        return decision

    def _agreement_score(self, ballots: list[AgentBallot]) -> float:
        """How much the agents agree (0 = total split, 1 = unanimous)."""
        if not ballots:
            return 0.0
        votes = [b.vote for b in ballots if b.vote != Vote.ABSTAIN]
        if not votes:
            return 0.0
        from collections import Counter
        counts = Counter(votes)
        most_common_count = counts.most_common(1)[0][1]
        return most_common_count / len(votes)

    # ── Diversity Scoring ─────────────────────────────────────────────

    def diversity_score(self) -> dict[str, Any]:
        """Assess how diverse the voting panel is."""
        voters = list(self._voters.values())
        if not voters:
            return {"score": 0.0, "voters": 0}

        models = set(v.model for v in voters if v.model)
        roles = set(v.role for v in voters)
        all_expertise = set()
        for v in voters:
            all_expertise.update(v.expertise_areas)

        model_diversity = len(models) / max(len(voters), 1)
        role_diversity = len(roles) / len(AgentRole)
        expertise_diversity = min(1.0, len(all_expertise) / 10)

        overall = (model_diversity + role_diversity + expertise_diversity) / 3

        return {
            "score": overall,
            "voters": len(voters),
            "unique_models": len(models),
            "unique_roles": len(roles),
            "expertise_areas": len(all_expertise),
            "model_diversity": model_diversity,
            "role_diversity": role_diversity,
        }

    # ── Analytics ─────────────────────────────────────────────────────

    def decision_stats(self) -> dict[str, Any]:
        """Aggregate statistics across all decisions."""
        if not self._decisions:
            return {"total_decisions": 0}

        outcomes: dict[str, int] = {}
        for d in self._decisions:
            outcomes[d.outcome] = outcomes.get(d.outcome, 0) + 1

        avg_rounds = sum(d.rounds_needed for d in self._decisions) / len(self._decisions)
        avg_ballots = sum(len(d.ballots) for d in self._decisions) / len(self._decisions)
        dissent_count = sum(1 for d in self._decisions if d.dissenting_opinions)

        return {
            "total_decisions": len(self._decisions),
            "outcome_breakdown": outcomes,
            "avg_rounds_to_decision": avg_rounds,
            "avg_ballots_per_decision": avg_ballots,
            "decisions_with_dissent": dissent_count,
            "dissent_rate": dissent_count / len(self._decisions),
        }

    def agent_agreement_matrix(self) -> dict[str, dict[str, float]]:
        """How often each pair of agents agrees."""
        agent_ids = list(self._voters.keys())
        matrix: dict[str, dict[str, float]] = {}

        for d in self._decisions:
            agent_votes: dict[str, Vote] = {}
            # Use latest ballot per agent
            for b in d.ballots:
                agent_votes[b.agent_id] = b.vote

            for i, a1 in enumerate(agent_ids):
                for a2 in agent_ids[i + 1:]:
                    if a1 in agent_votes and a2 in agent_votes:
                        key = f"{a1}:{a2}"
                        if key not in matrix:
                            matrix[key] = {"agree": 0, "total": 0}
                        matrix[key]["total"] += 1
                        if agent_votes[a1] == agent_votes[a2]:
                            matrix[key]["agree"] += 1

        # Convert to rates
        result: dict[str, dict[str, float]] = {}
        for key, data in matrix.items():
            result[key] = {
                "agreement_rate": data["agree"] / data["total"] if data["total"] else 0,
                "total_decisions": data["total"],
            }
        return result
