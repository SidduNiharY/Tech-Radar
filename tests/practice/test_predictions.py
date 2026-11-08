from __future__ import annotations

from datetime import datetime

import pytest

from techradar.practice.predictions import PredictionTracker


def test_take_only_for_known_briefing_message():
    tracker = PredictionTracker()
    valid_ids = {101, 102, 103}

    # Valid message_id succeeds
    take = tracker.record_take(
        briefing_id="briefing_2026_11_08",
        message_id=102,
        user_text="Inflation will cool off in Q2 2027.",
        valid_briefing_message_ids=valid_ids,
    )
    assert take["briefing_id"] == "briefing_2026_11_08"
    assert take["message_id"] == 102
    assert take["text"] == "Inflation will cool off in Q2 2027."
    assert isinstance(take["created_at"], datetime)

    # Invalid message_id raises ValueError
    with pytest.raises(ValueError, match="Reply must be to an active briefing message"):
        tracker.record_take(
            briefing_id="briefing_2026_11_08",
            message_id=999,
            user_text="Invalid message reply",
            valid_briefing_message_ids=valid_ids,
        )


def test_take_max_length_enforced():
    tracker = PredictionTracker()
    valid_ids = {201}

    # Exactly 500 characters succeeds
    text_500 = "a" * 500
    take = tracker.record_take(
        briefing_id="briefing_2026_11_08",
        message_id=201,
        user_text=text_500,
        valid_briefing_message_ids=valid_ids,
    )
    assert len(take["text"]) == 500

    # 501 characters is rejected
    text_501 = "a" * 501
    with pytest.raises(ValueError, match="User text exceeds maximum length of 500 characters"):
        tracker.record_take(
            briefing_id="briefing_2026_11_08",
            message_id=201,
            user_text=text_501,
            valid_briefing_message_ids=valid_ids,
        )


def test_prediction_tracker_stores_and_retrieves():
    tracker = PredictionTracker()
    valid_ids = {301, 302}

    tracker.record_take(
        briefing_id="b1",
        message_id=301,
        user_text="Take 1",
        valid_briefing_message_ids=valid_ids,
    )
    tracker.record_take(
        briefing_id="b1",
        message_id=302,
        user_text="Take 2",
        valid_briefing_message_ids=valid_ids,
    )

    takes = tracker.get_takes()
    assert len(takes) == 2
    assert takes[0]["text"] == "Take 1"
    assert takes[1]["text"] == "Take 2"


def test_prediction_tracker_class_invocation():
    valid_ids = {401}
    take = PredictionTracker.record_take(
        briefing_id="b_class",
        message_id=401,
        user_text="Direct class invocation works.",
        valid_briefing_message_ids=valid_ids,
    )
    assert take["briefing_id"] == "b_class"
    assert take["message_id"] == 401
