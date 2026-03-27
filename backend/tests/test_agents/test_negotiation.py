"""Tests for negotiation workflow — create, generate alternatives, select, stats."""

from __future__ import annotations

import uuid

import pytest

from app.agents.negotiation import (
    NegotiationStatus,
    clear_negotiations,
    create_negotiation,
    escalate_negotiation,
    generate_alternatives,
    get_negotiation,
    get_negotiation_stats,
    negotiation_to_json,
    select_alternative,
    withdraw_negotiation,
)


@pytest.fixture(autouse=True)
def _clean_store() -> None:
    clear_negotiations()


class TestCreateNegotiation:
    def test_creates_with_required_fields(self) -> None:
        review_id = uuid.uuid4()
        neg = create_negotiation(
            review_id=review_id,
            finding_index=0,
            original_suggestion="Use type hints",
            rejection_reason="Too verbose",
        )
        assert neg.review_id == review_id
        assert neg.finding_index == 0
        assert neg.status == NegotiationStatus.PENDING

    def test_assigns_unique_id(self) -> None:
        n1 = create_negotiation(uuid.uuid4(), 0, "s1", "r1")
        n2 = create_negotiation(uuid.uuid4(), 0, "s2", "r2")
        assert n1.id != n2.id

    def test_stores_negotiation(self) -> None:
        neg = create_negotiation(uuid.uuid4(), 0, "s", "r")
        assert get_negotiation(neg.id) is neg


class TestGenerateAlternatives:
    def test_generates_performance_alternative(self) -> None:
        neg = create_negotiation(uuid.uuid4(), 0, "Add caching", "Too much overhead")
        alts = generate_alternatives(neg.id, "Too much overhead", "Add caching")
        assert any(a.id == "perf-optimized" for a in alts)

    def test_generates_simplified_alternative(self) -> None:
        neg = create_negotiation(uuid.uuid4(), 0, "Refactor", "Too complex")
        alts = generate_alternatives(neg.id, "Too complex", "Refactor")
        assert any(a.id == "simplified" for a in alts)

    def test_generates_backward_compat_alternative(self) -> None:
        neg = create_negotiation(uuid.uuid4(), 0, "Change API", "Breaking change")
        alts = generate_alternatives(neg.id, "Breaking change", "Change API")
        assert any(a.id == "backward-compat" for a in alts)

    def test_generates_test_first_alternative(self) -> None:
        neg = create_negotiation(uuid.uuid4(), 0, "Rename func", "No tests for this")
        alts = generate_alternatives(neg.id, "No tests for this", "Rename func")
        assert any(a.id == "test-first" for a in alts)

    def test_always_includes_defer_option(self) -> None:
        neg = create_negotiation(uuid.uuid4(), 0, "x", "random reason")
        alts = generate_alternatives(neg.id, "random reason", "x")
        assert any(a.id == "defer" for a in alts)

    def test_sets_status_to_alternatives_proposed(self) -> None:
        neg = create_negotiation(uuid.uuid4(), 0, "x", "reason")
        generate_alternatives(neg.id, "reason", "x")
        assert neg.status == NegotiationStatus.ALTERNATIVES_PROPOSED

    def test_respects_max_alternatives(self) -> None:
        neg = create_negotiation(uuid.uuid4(), 0, "x", "performance")
        alts = generate_alternatives(neg.id, "performance", "x", max_alternatives=2)
        assert len(alts) <= 2

    def test_raises_for_unknown_negotiation(self) -> None:
        with pytest.raises(ValueError, match="not found"):
            generate_alternatives(uuid.uuid4(), "r", "s")

    def test_alternatives_have_trade_offs(self) -> None:
        neg = create_negotiation(uuid.uuid4(), 0, "x", "Too slow overhead")
        alts = generate_alternatives(neg.id, "Too slow overhead", "x")
        for alt in alts:
            assert isinstance(alt.trade_offs, list)


class TestSelectAlternative:
    def test_select_original(self) -> None:
        neg = create_negotiation(uuid.uuid4(), 0, "s", "r")
        generate_alternatives(neg.id, "r", "s")
        result = select_alternative(neg.id, "original")
        assert result.status == NegotiationStatus.ACCEPTED
        assert result.selected_alternative_id is None

    def test_select_valid_alternative(self) -> None:
        neg = create_negotiation(uuid.uuid4(), 0, "s", "r")
        alts = generate_alternatives(neg.id, "r", "s")
        result = select_alternative(neg.id, alts[0].id)
        assert result.status == NegotiationStatus.ACCEPTED
        assert result.selected_alternative_id == alts[0].id

    def test_raises_for_invalid_alternative(self) -> None:
        neg = create_negotiation(uuid.uuid4(), 0, "s", "r")
        generate_alternatives(neg.id, "r", "s")
        with pytest.raises(ValueError, match="not found"):
            select_alternative(neg.id, "nonexistent")

    def test_raises_for_unknown_negotiation(self) -> None:
        with pytest.raises(ValueError, match="not found"):
            select_alternative(uuid.uuid4(), "original")

    def test_sets_resolved_at(self) -> None:
        neg = create_negotiation(uuid.uuid4(), 0, "s", "r")
        generate_alternatives(neg.id, "r", "s")
        result = select_alternative(neg.id, "original")
        assert result.resolved_at is not None


class TestEscalateAndWithdraw:
    def test_escalate_sets_status(self) -> None:
        neg = create_negotiation(uuid.uuid4(), 0, "s", "r")
        result = escalate_negotiation(neg.id)
        assert result.status == NegotiationStatus.ESCALATED

    def test_withdraw_sets_status(self) -> None:
        neg = create_negotiation(uuid.uuid4(), 0, "s", "r")
        result = withdraw_negotiation(neg.id)
        assert result.status == NegotiationStatus.WITHDRAWN

    def test_escalate_raises_for_unknown(self) -> None:
        with pytest.raises(ValueError):
            escalate_negotiation(uuid.uuid4())

    def test_withdraw_raises_for_unknown(self) -> None:
        with pytest.raises(ValueError):
            withdraw_negotiation(uuid.uuid4())


class TestNegotiationStats:
    def test_empty_stats(self) -> None:
        stats = get_negotiation_stats()
        assert stats["total_negotiations"] == 0

    def test_tracks_original_accepted(self) -> None:
        neg = create_negotiation(uuid.uuid4(), 0, "s", "r")
        generate_alternatives(neg.id, "r", "s")
        select_alternative(neg.id, "original")

        stats = get_negotiation_stats()
        assert stats["total_negotiations"] == 1
        assert stats["original_accepted_rate"] == 100.0

    def test_tracks_alternative_selected(self) -> None:
        neg = create_negotiation(uuid.uuid4(), 0, "s", "r")
        alts = generate_alternatives(neg.id, "r", "s")
        select_alternative(neg.id, alts[0].id)

        stats = get_negotiation_stats()
        assert stats["alternative_selected_rate"] == 100.0
        assert alts[0].id in stats["most_selected_alternatives"]


class TestNegotiationToJson:
    def test_serializes_complete_negotiation(self) -> None:
        rid = uuid.uuid4()
        neg = create_negotiation(rid, 0, "suggestion", "reason")
        generate_alternatives(neg.id, "reason", "suggestion")

        data = negotiation_to_json(neg)
        assert data["review_id"] == str(rid)
        assert data["status"] == "alternatives_proposed"
        assert len(data["alternatives"]) > 0
        assert "trade_offs" in data["alternatives"][0]
