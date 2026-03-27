"""Tests for developer feedback tracker module."""

from __future__ import annotations

import uuid

import pytest

from app.quality.feedback_tracker import (
    FeedbackAction,
    FeedbackStats,
    clear_feedback,
    get_feedback_for_review,
    get_feedback_stats,
    get_rejection_reasons,
    record_feedback,
)


@pytest.fixture(autouse=True)
def _clean_feedback() -> None:
    """Clear feedback store before each test."""
    clear_feedback()


class TestRecordFeedback:
    def test_record_accepted(self) -> None:
        review_id = uuid.uuid4()
        fb = record_feedback(review_id, 0, FeedbackAction.ACCEPTED)
        assert fb.review_id == review_id
        assert fb.finding_index == 0
        assert fb.action == FeedbackAction.ACCEPTED

    def test_record_rejected_with_reason(self) -> None:
        review_id = uuid.uuid4()
        fb = record_feedback(review_id, 1, FeedbackAction.REJECTED, reason="false positive")
        assert fb.action == FeedbackAction.REJECTED
        assert fb.reason == "false positive"

    def test_record_deferred(self) -> None:
        review_id = uuid.uuid4()
        fb = record_feedback(review_id, 2, FeedbackAction.DEFERRED)
        assert fb.action == FeedbackAction.DEFERRED

    def test_multiple_feedbacks_same_review(self) -> None:
        review_id = uuid.uuid4()
        record_feedback(review_id, 0, FeedbackAction.ACCEPTED)
        record_feedback(review_id, 1, FeedbackAction.REJECTED)
        feedbacks = get_feedback_for_review(review_id)
        assert len(feedbacks) == 2


class TestGetFeedbackForReview:
    def test_returns_empty_for_unknown_review(self) -> None:
        result = get_feedback_for_review(uuid.uuid4())
        assert result == []

    def test_returns_correct_feedbacks(self) -> None:
        review_id = uuid.uuid4()
        record_feedback(review_id, 0, FeedbackAction.ACCEPTED)
        result = get_feedback_for_review(review_id)
        assert len(result) == 1
        assert result[0].finding_index == 0


class TestGetFeedbackStats:
    def test_empty_stats(self) -> None:
        stats = get_feedback_stats()
        assert stats.total_findings == 0
        assert stats.acceptance_rate == 0.0

    def test_counts_correctly(self) -> None:
        r1 = uuid.uuid4()
        r2 = uuid.uuid4()
        record_feedback(r1, 0, FeedbackAction.ACCEPTED)
        record_feedback(r1, 1, FeedbackAction.ACCEPTED)
        record_feedback(r2, 0, FeedbackAction.REJECTED, reason="not relevant")
        record_feedback(r2, 1, FeedbackAction.DEFERRED)

        stats = get_feedback_stats()
        assert stats.total_findings == 4
        assert stats.accepted == 2
        assert stats.rejected == 1
        assert stats.deferred == 1
        assert stats.acceptance_rate == 50.0
        assert stats.rejection_rate == 25.0


class TestGetRejectionReasons:
    def test_empty_reasons(self) -> None:
        reasons = get_rejection_reasons()
        assert reasons == {}

    def test_aggregates_reasons(self) -> None:
        r1, r2 = uuid.uuid4(), uuid.uuid4()
        record_feedback(r1, 0, FeedbackAction.REJECTED, reason="false positive")
        record_feedback(r1, 1, FeedbackAction.REJECTED, reason="false positive")
        record_feedback(r2, 0, FeedbackAction.REJECTED, reason="not actionable")

        reasons = get_rejection_reasons()
        assert reasons["false positive"] == 2
        assert reasons["not actionable"] == 1
        # Most frequent first
        assert list(reasons.keys())[0] == "false positive"

    def test_ignores_accepted_feedback(self) -> None:
        record_feedback(uuid.uuid4(), 0, FeedbackAction.ACCEPTED, reason="good catch")
        reasons = get_rejection_reasons()
        assert reasons == {}


class TestFeedbackStats:
    def test_acceptance_rate_zero_division(self) -> None:
        stats = FeedbackStats()
        assert stats.acceptance_rate == 0.0
        assert stats.rejection_rate == 0.0

    def test_rates_calculation(self) -> None:
        stats = FeedbackStats(total_findings=10, accepted=7, rejected=2, deferred=1)
        assert stats.acceptance_rate == 70.0
        assert stats.rejection_rate == 20.0


class TestClearFeedback:
    def test_clears_all(self) -> None:
        record_feedback(uuid.uuid4(), 0, FeedbackAction.ACCEPTED)
        clear_feedback()
        stats = get_feedback_stats()
        assert stats.total_findings == 0
