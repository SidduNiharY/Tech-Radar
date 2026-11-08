"""Unit tests for user feedback and source weight adjustment engine."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from techradar.pipeline.feedback import (
    FeedbackRecord,
    FeedbackType,
    SourceWeightManager,
)


def test_feedback_type_enum_values():
    """Verify all defined feedback types exist and match string values."""
    assert FeedbackType.THUMBS_UP == "thumbs_up"
    assert FeedbackType.THUMBS_DOWN == "thumbs_down"
    assert FeedbackType.TOO_LONG == "too_long"
    assert FeedbackType.WRONG_FACT == "wrong_fact"
    assert FeedbackType.OFF_TOPIC == "off_topic"


def test_feedback_record_creation_and_defaults():
    """Verify FeedbackRecord creation, default values, and field retention."""
    rec = FeedbackRecord(
        id="fb-001",
        item_id="ans-42",
        feedback_type=FeedbackType.THUMBS_UP,
    )
    assert rec.id == "fb-001"
    assert rec.item_id == "ans-42"
    assert rec.feedback_type == FeedbackType.THUMBS_UP
    assert rec.notes == ""
    assert isinstance(rec.created_at, datetime)
    assert rec.created_at.tzinfo == UTC

    custom_time = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)
    rec_custom = FeedbackRecord(
        id="fb-002",
        item_id="quiz-10",
        feedback_type=FeedbackType.WRONG_FACT,
        notes="Outdated RBI repo rate",
        created_at=custom_time,
    )
    assert rec_custom.notes == "Outdated RBI repo rate"
    assert rec_custom.created_at == custom_time


def test_feedback_record_enum_validation():
    """Verify validation errors on invalid feedback types or missing required fields."""
    with pytest.raises(ValidationError):
        FeedbackRecord(
            id="fb-err",
            item_id="ans-1",
            feedback_type="completely_invalid",  # type: ignore[arg-type]
        )

    with pytest.raises(ValidationError):
        FeedbackRecord(
            item_id="ans-1",  # missing id
            feedback_type=FeedbackType.THUMBS_UP,  # type: ignore[call-arg]
        )


def test_source_weight_increase_and_decrease_within_bounds():
    """Verify weight changes within normal [0.2, 2.0] range."""
    manager = SourceWeightManager()
    domain = "techblog.example"

    # Default weight before any adjustment
    assert manager.get_source_weight(domain) == 1.0

    # Positive delta increases weight
    w1 = manager.update_source_weight(domain, 0.4)
    assert w1 == 1.4
    assert manager.get_source_weight(domain) == 1.4

    # Negative delta decreases weight
    w2 = manager.update_source_weight(domain, -0.6)
    assert w2 == 0.8
    assert manager.get_source_weight(domain) == 0.8


def test_official_source_floor():
    """Verify official sources cannot drop below 1.0 even with large negative delta."""
    manager = SourceWeightManager()

    # Pre-configured official domain: pib.gov.in
    w_pib = manager.update_source_weight("pib.gov.in", -5.0)
    assert w_pib == 1.0
    assert manager.get_source_weight("pib.gov.in") == 1.0

    # Pre-configured official domain: rbi.org.in
    w_rbi = manager.update_source_weight("rbi.org.in", -0.5)
    assert w_rbi == 1.0

    # Explicit is_official=True on arbitrary domain
    w_custom = manager.update_source_weight("who.int", -10.0, is_official=True)
    assert w_custom == 1.0

    # Official source can still increase up to 2.0
    w_pib_up = manager.update_source_weight("pib.gov.in", 0.5)
    assert w_pib_up == 1.5


def test_non_official_source_bounds():
    """Verify non-official sources clamp strictly between 0.2 and 2.0."""
    manager = SourceWeightManager()
    domain = "untrusted-rumor.com"

    # Negative delta clamped at 0.2
    w_low = manager.update_source_weight(domain, -5.0)
    assert w_low == 0.2
    assert manager.get_source_weight(domain) == 0.2

    # Further negative updates stay clamped at 0.2
    w_low_again = manager.update_source_weight(domain, -1.0)
    assert w_low_again == 0.2

    # Positive delta clamped at 2.0
    w_high = manager.update_source_weight(domain, 5.0)
    assert w_high == 2.0
    assert manager.get_source_weight(domain) == 2.0

    # Further positive updates stay clamped at 2.0
    w_high_again = manager.update_source_weight(domain, 1.0)
    assert w_high_again == 2.0


def test_record_regression_case():
    """Verify recording regression test cases with feedback metadata."""
    manager = SourceWeightManager()
    assert len(manager.regression_cases) == 0

    case1 = manager.record_regression_case(
        item_id="ans-99",
        feedback_type=FeedbackType.WRONG_FACT,
        original_output="Repo rate is 6.50%",
        correction="Repo rate is 6.25%",
    )

    assert case1["item_id"] == "ans-99"
    assert case1["feedback_type"] == FeedbackType.WRONG_FACT
    assert case1["original_output"] == "Repo rate is 6.50%"
    assert case1["correction"] == "Repo rate is 6.25%"
    assert isinstance(case1["created_at"], datetime)
    assert "id" in case1

    # String feedback type also converts successfully
    case2 = manager.record_regression_case(
        item_id="quiz-5",
        feedback_type="too_long",
        original_output="Excessive 500-word explanation...",
        correction="Concise 50-word explanation",
    )
    assert case2["feedback_type"] == FeedbackType.TOO_LONG

    # Stored cases history
    assert len(manager.regression_cases) == 2
    assert manager.regression_cases[0]["id"] == case1["id"]
    assert manager.regression_cases[1]["id"] == case2["id"]

    # Invalid feedback type raises ValueError
    with pytest.raises(ValueError):
        manager.record_regression_case(
            item_id="ans-invalid",
            feedback_type="invalid_type",
            original_output="foo",
            correction="bar",
        )
