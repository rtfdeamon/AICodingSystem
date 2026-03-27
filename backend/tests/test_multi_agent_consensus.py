"""Tests for Multi-Agent Consensus Protocol."""

from __future__ import annotations

import pytest

from app.quality.multi_agent_consensus import (
    AgentRole,
    ConsensusOutcome,
    MultiAgentConsensus,
    Vote,
    VotingStrategy,
)

# ── Voter Management ─────────────────────────────────────────────────────

class TestVoterManagement:
    def test_register_voter(self):
        mac = MultiAgentConsensus()
        voter = mac.register_voter("claude", role=AgentRole.REVIEWER, model="claude-sonnet-4-6")
        assert voter.name == "claude"
        assert voter.model == "claude-sonnet-4-6"

    def test_get_voter(self):
        mac = MultiAgentConsensus()
        voter = mac.register_voter("claude")
        assert mac.get_voter(voter.id) is not None

    def test_get_missing_voter(self):
        mac = MultiAgentConsensus()
        assert mac.get_voter("missing") is None

    def test_list_voters(self):
        mac = MultiAgentConsensus()
        mac.register_voter("a")
        mac.register_voter("b")
        assert len(mac.list_voters()) == 2


# ── Voting ────────────────────────────────────────────────────────────────

class TestVoting:
    def test_cast_vote(self):
        mac = MultiAgentConsensus()
        voter = mac.register_voter("claude")
        ballot = mac.cast_vote(voter.id, Vote.APPROVE, confidence=0.9, reasoning="Looks good")
        assert ballot.vote == Vote.APPROVE
        assert ballot.confidence == 0.9

    def test_cast_vote_unregistered(self):
        mac = MultiAgentConsensus()
        with pytest.raises(ValueError, match="not registered"):
            mac.cast_vote("unregistered", Vote.APPROVE)

    def test_confidence_clamped(self):
        mac = MultiAgentConsensus()
        voter = mac.register_voter("claude")
        ballot = mac.cast_vote(voter.id, Vote.APPROVE, confidence=1.5)
        assert ballot.confidence == 1.0
        ballot2 = mac.cast_vote(voter.id, Vote.APPROVE, confidence=-0.5)
        assert ballot2.confidence == 0.0


# ── Majority Voting ───────────────────────────────────────────────────────

class TestMajorityVoting:
    def test_majority_approve(self):
        mac = MultiAgentConsensus(strategy=VotingStrategy.MAJORITY)
        v1 = mac.register_voter("a")
        v2 = mac.register_voter("b")
        v3 = mac.register_voter("c")
        ballots = [
            mac.cast_vote(v1.id, Vote.APPROVE),
            mac.cast_vote(v2.id, Vote.APPROVE),
            mac.cast_vote(v3.id, Vote.REJECT),
        ]
        decision = mac.decide("review PR #42", ballots)
        assert decision.outcome == ConsensusOutcome.APPROVED

    def test_majority_reject(self):
        mac = MultiAgentConsensus(strategy=VotingStrategy.MAJORITY)
        v1 = mac.register_voter("a")
        v2 = mac.register_voter("b")
        v3 = mac.register_voter("c")
        ballots = [
            mac.cast_vote(v1.id, Vote.REJECT),
            mac.cast_vote(v2.id, Vote.REJECT),
            mac.cast_vote(v3.id, Vote.APPROVE),
        ]
        decision = mac.decide("review PR #42", ballots)
        assert decision.outcome == ConsensusOutcome.REJECTED

    def test_majority_split(self):
        mac = MultiAgentConsensus(strategy=VotingStrategy.MAJORITY)
        v1 = mac.register_voter("a")
        v2 = mac.register_voter("b")
        ballots = [
            mac.cast_vote(v1.id, Vote.APPROVE),
            mac.cast_vote(v2.id, Vote.REJECT),
        ]
        decision = mac.decide("split vote", ballots)
        assert decision.outcome == ConsensusOutcome.NO_CONSENSUS


# ── Unanimous Voting ──────────────────────────────────────────────────────

class TestUnanimousVoting:
    def test_unanimous_approve(self):
        mac = MultiAgentConsensus(strategy=VotingStrategy.UNANIMOUS)
        v1 = mac.register_voter("a")
        v2 = mac.register_voter("b")
        ballots = [
            mac.cast_vote(v1.id, Vote.APPROVE),
            mac.cast_vote(v2.id, Vote.APPROVE),
        ]
        decision = mac.decide("deploy", ballots)
        assert decision.outcome == ConsensusOutcome.APPROVED

    def test_unanimous_fails_with_one_reject(self):
        mac = MultiAgentConsensus(strategy=VotingStrategy.UNANIMOUS)
        v1 = mac.register_voter("a")
        v2 = mac.register_voter("b")
        v3 = mac.register_voter("c")
        ballots = [
            mac.cast_vote(v1.id, Vote.APPROVE),
            mac.cast_vote(v2.id, Vote.APPROVE),
            mac.cast_vote(v3.id, Vote.REJECT),
        ]
        decision = mac.decide("deploy", ballots)
        assert decision.outcome == ConsensusOutcome.NO_CONSENSUS

    def test_unanimous_reject(self):
        mac = MultiAgentConsensus(strategy=VotingStrategy.UNANIMOUS)
        v1 = mac.register_voter("a")
        v2 = mac.register_voter("b")
        ballots = [
            mac.cast_vote(v1.id, Vote.REJECT),
            mac.cast_vote(v2.id, Vote.REJECT),
        ]
        decision = mac.decide("deploy", ballots)
        assert decision.outcome == ConsensusOutcome.REJECTED


# ── Supermajority Voting ──────────────────────────────────────────────────

class TestSupermajorityVoting:
    def test_supermajority_approve(self):
        mac = MultiAgentConsensus(strategy=VotingStrategy.SUPERMAJORITY)
        voters = [mac.register_voter(f"v{i}") for i in range(3)]
        ballots = [
            mac.cast_vote(voters[0].id, Vote.APPROVE),
            mac.cast_vote(voters[1].id, Vote.APPROVE),
            mac.cast_vote(voters[2].id, Vote.REJECT),
        ]
        decision = mac.decide("merge", ballots)
        assert decision.outcome == ConsensusOutcome.APPROVED

    def test_supermajority_no_consensus(self):
        mac = MultiAgentConsensus(strategy=VotingStrategy.SUPERMAJORITY)
        voters = [mac.register_voter(f"v{i}") for i in range(4)]
        ballots = [
            mac.cast_vote(voters[0].id, Vote.APPROVE),
            mac.cast_vote(voters[1].id, Vote.APPROVE),
            mac.cast_vote(voters[2].id, Vote.REJECT),
            mac.cast_vote(voters[3].id, Vote.REJECT),
        ]
        decision = mac.decide("merge", ballots)
        assert decision.outcome == ConsensusOutcome.NO_CONSENSUS


# ── Weighted Voting ───────────────────────────────────────────────────────

class TestWeightedVoting:
    def test_weighted_approve(self):
        mac = MultiAgentConsensus(strategy=VotingStrategy.WEIGHTED)
        senior = mac.register_voter("senior", weight=3.0)
        junior = mac.register_voter("junior", weight=1.0)
        ballots = [
            mac.cast_vote(senior.id, Vote.APPROVE, confidence=0.9),
            mac.cast_vote(junior.id, Vote.REJECT, confidence=0.6),
        ]
        decision = mac.decide("complex change", ballots)
        assert decision.outcome == ConsensusOutcome.APPROVED

    def test_weighted_reject(self):
        mac = MultiAgentConsensus(strategy=VotingStrategy.WEIGHTED)
        v1 = mac.register_voter("a", weight=1.0)
        v2 = mac.register_voter("b", weight=5.0)
        ballots = [
            mac.cast_vote(v1.id, Vote.APPROVE, confidence=0.9),
            mac.cast_vote(v2.id, Vote.REJECT, confidence=0.9),
        ]
        decision = mac.decide("change", ballots)
        assert decision.outcome == ConsensusOutcome.REJECTED


# ── Quorum Voting ─────────────────────────────────────────────────────────

class TestQuorumVoting:
    def test_quorum_met(self):
        mac = MultiAgentConsensus(strategy=VotingStrategy.QUORUM, quorum_threshold=0.6)
        v1 = mac.register_voter("a")
        v2 = mac.register_voter("b")
        mac.register_voter("c")
        ballots = [
            mac.cast_vote(v1.id, Vote.APPROVE),
            mac.cast_vote(v2.id, Vote.APPROVE),
        ]
        decision = mac.decide("deploy", ballots)
        assert decision.outcome == ConsensusOutcome.APPROVED

    def test_quorum_not_met(self):
        mac = MultiAgentConsensus(strategy=VotingStrategy.QUORUM, quorum_threshold=0.8)
        voters = [mac.register_voter(f"v{i}") for i in range(5)]
        ballots = [
            mac.cast_vote(voters[0].id, Vote.APPROVE),
            mac.cast_vote(voters[1].id, Vote.APPROVE),
        ]
        decision = mac.decide("deploy", ballots)
        assert decision.outcome == ConsensusOutcome.NO_CONSENSUS


# ── Low Confidence Filtering ─────────────────────────────────────────────

class TestConfidenceFiltering:
    def test_low_confidence_filtered(self):
        mac = MultiAgentConsensus(confidence_threshold=0.6)
        v1 = mac.register_voter("a")
        v2 = mac.register_voter("b")
        v3 = mac.register_voter("c")
        ballots = [
            mac.cast_vote(v1.id, Vote.APPROVE, confidence=0.9),
            mac.cast_vote(v2.id, Vote.APPROVE, confidence=0.8),
            mac.cast_vote(v3.id, Vote.REJECT, confidence=0.3),  # filtered
        ]
        decision = mac.decide("test", ballots)
        assert decision.outcome == ConsensusOutcome.APPROVED

    def test_all_low_confidence(self):
        mac = MultiAgentConsensus(confidence_threshold=0.9)
        v1 = mac.register_voter("a")
        ballots = [mac.cast_vote(v1.id, Vote.APPROVE, confidence=0.5)]
        decision = mac.decide("test", ballots)
        assert decision.outcome == ConsensusOutcome.NO_CONSENSUS

    def test_abstains_filtered(self):
        mac = MultiAgentConsensus()
        v1 = mac.register_voter("a")
        v2 = mac.register_voter("b")
        ballots = [
            mac.cast_vote(v1.id, Vote.APPROVE),
            mac.cast_vote(v2.id, Vote.ABSTAIN),
        ]
        decision = mac.decide("test", ballots)
        assert decision.outcome == ConsensusOutcome.APPROVED


# ── Escalation ────────────────────────────────────────────────────────────

class TestEscalation:
    def test_needs_discussion_escalates(self):
        mac = MultiAgentConsensus()
        v1 = mac.register_voter("a")
        v2 = mac.register_voter("b")
        v3 = mac.register_voter("c")
        ballots = [
            mac.cast_vote(v1.id, Vote.NEEDS_DISCUSSION),
            mac.cast_vote(v2.id, Vote.NEEDS_DISCUSSION),
            mac.cast_vote(v3.id, Vote.APPROVE),
        ]
        decision = mac.decide("complex", ballots)
        assert decision.outcome == ConsensusOutcome.ESCALATED


# ── Dissenting Opinions ──────────────────────────────────────────────────

class TestDissentingOpinions:
    def test_dissent_captured_on_approve(self):
        mac = MultiAgentConsensus()
        v1 = mac.register_voter("a")
        v2 = mac.register_voter("b")
        v3 = mac.register_voter("c")
        ballots = [
            mac.cast_vote(v1.id, Vote.APPROVE),
            mac.cast_vote(v2.id, Vote.APPROVE),
            mac.cast_vote(v3.id, Vote.REJECT, reasoning="Security concern"),
        ]
        decision = mac.decide("test", ballots)
        assert decision.outcome == ConsensusOutcome.APPROVED
        assert "Security concern" in decision.dissenting_opinions


# ── Deliberation ──────────────────────────────────────────────────────────

class TestDeliberation:
    def test_multi_round_deliberation(self):
        mac = MultiAgentConsensus()
        v1 = mac.register_voter("a")
        v2 = mac.register_voter("b")
        v3 = mac.register_voter("c")

        round1 = [
            mac.cast_vote(v1.id, Vote.APPROVE),
            mac.cast_vote(v2.id, Vote.REJECT),
            mac.cast_vote(v3.id, Vote.REJECT),
        ]
        round2 = [
            mac.cast_vote(v1.id, Vote.APPROVE),
            mac.cast_vote(v2.id, Vote.APPROVE),  # changed mind
            mac.cast_vote(v3.id, Vote.APPROVE),  # changed mind
        ]
        decision = mac.run_deliberation("PR #42", [round1, round2])
        assert decision.outcome == ConsensusOutcome.APPROVED
        assert decision.rounds_needed == 2

    def test_deliberation_tracks_opinion_changes(self):
        mac = MultiAgentConsensus()
        v1 = mac.register_voter("a")
        round1 = [mac.cast_vote(v1.id, Vote.REJECT)]
        round2 = [mac.cast_vote(v1.id, Vote.APPROVE)]
        decision = mac.run_deliberation("test", [round1, round2])
        revised = [b for b in decision.ballots if b.revised_from is not None]
        assert len(revised) == 1
        assert revised[0].revised_from == Vote.REJECT

    def test_deliberation_empty_rounds(self):
        mac = MultiAgentConsensus()
        with pytest.raises(ValueError):
            mac.run_deliberation("test", [])


# ── Diversity Scoring ─────────────────────────────────────────────────────

class TestDiversityScoring:
    def test_diverse_panel(self):
        mac = MultiAgentConsensus()
        mac.register_voter(
            "claude", role=AgentRole.REVIEWER,
            model="claude-sonnet-4-6", expertise_areas=["python"],
        )
        mac.register_voter(
            "gpt", role=AgentRole.SECURITY_AUDITOR,
            model="gpt-4o", expertise_areas=["security"],
        )
        mac.register_voter(
            "gemini", role=AgentRole.ARCHITECT,
            model="gemini-2.0", expertise_areas=["architecture"],
        )
        score = mac.diversity_score()
        assert score["score"] > 0.3
        assert score["unique_models"] == 3

    def test_homogeneous_panel(self):
        mac = MultiAgentConsensus()
        mac.register_voter("a", model="same-model")
        mac.register_voter("b", model="same-model")
        score = mac.diversity_score()
        assert score["unique_models"] == 1

    def test_empty_panel(self):
        mac = MultiAgentConsensus()
        score = mac.diversity_score()
        assert score["score"] == 0.0


# ── Analytics ─────────────────────────────────────────────────────────────

class TestAnalytics:
    def test_decision_stats(self):
        mac = MultiAgentConsensus()
        v1 = mac.register_voter("a")
        v2 = mac.register_voter("b")
        ballots = [
            mac.cast_vote(v1.id, Vote.APPROVE),
            mac.cast_vote(v2.id, Vote.APPROVE),
        ]
        mac.decide("test1", ballots)
        mac.decide("test2", ballots)
        stats = mac.decision_stats()
        assert stats["total_decisions"] == 2
        assert stats["outcome_breakdown"][ConsensusOutcome.APPROVED] == 2

    def test_empty_decision_stats(self):
        mac = MultiAgentConsensus()
        stats = mac.decision_stats()
        assert stats["total_decisions"] == 0

    def test_agreement_matrix(self):
        mac = MultiAgentConsensus()
        v1 = mac.register_voter("a")
        v2 = mac.register_voter("b")
        ballots = [
            mac.cast_vote(v1.id, Vote.APPROVE),
            mac.cast_vote(v2.id, Vote.APPROVE),
        ]
        mac.decide("test", ballots)
        matrix = mac.agent_agreement_matrix()
        assert len(matrix) > 0
