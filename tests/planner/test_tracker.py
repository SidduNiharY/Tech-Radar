from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from pydantic import ValidationError

from techradar.planner.tracker import GoalType, StudySession, StudyTimeTracker


def test_goal_type_values_and_members():
    assert GoalType.GATE == "gate"
    assert GoalType.SSC == "ssc"
    assert GoalType.BANK == "bank"
    assert GoalType.DEV == "dev"
    assert GoalType.ENGLISH == "english"
    assert GoalType.WORLD == "world"

    # Case-insensitive instantiation and equality
    assert GoalType("GATE") == GoalType.GATE
    assert GoalType("gate") == GoalType.GATE
    assert GoalType.GATE == "GATE"
    assert GoalType.GATE == "gate"


def test_log_session_basic():
    tracker = StudyTimeTracker()
    session = tracker.log_session(
        goal=GoalType.GATE,
        duration_minutes=45,
        topics=["algorithms", "dynamic programming"],
    )

    assert isinstance(session, StudySession)
    assert session.goal == GoalType.GATE
    assert session.duration_minutes == 45
    assert session.topics_covered == ["algorithms", "dynamic programming"]
    assert len(session.id) > 0
    assert isinstance(session.timestamp, datetime)
    assert len(tracker.sessions) == 1
    assert tracker.sessions[0] == session


def test_log_session_default_topics_and_timestamp():
    tracker = StudyTimeTracker()
    before = datetime.now(UTC)
    session = tracker.log_session(goal=GoalType.DEV, duration_minutes=30)
    after = datetime.now(UTC)

    assert session.topics_covered == []
    assert before <= session.timestamp <= after
    assert len(tracker.sessions) == 1


def test_log_session_zero_duration_raises():
    tracker = StudyTimeTracker()
    with pytest.raises(ValueError, match="duration_minutes must be greater than 0"):
        tracker.log_session(goal=GoalType.SSC, duration_minutes=0)


def test_log_session_negative_duration_raises():
    tracker = StudyTimeTracker()
    with pytest.raises(ValueError, match="duration_minutes must be greater than 0"):
        tracker.log_session(goal=GoalType.BANK, duration_minutes=-15)


def test_study_session_model_validation():
    with pytest.raises(ValidationError):
        StudySession(id="s1", goal=GoalType.DEV, duration_minutes=0)

    with pytest.raises(ValidationError):
        StudySession(id="s2", goal=GoalType.DEV, duration_minutes=-10)


def test_get_total_minutes_by_goal_empty():
    tracker = StudyTimeTracker()
    assert tracker.get_total_minutes_by_goal() == {}


def test_get_total_minutes_by_goal_aggregation():
    tracker = StudyTimeTracker()
    tracker.log_session(goal=GoalType.GATE, duration_minutes=60)
    tracker.log_session(goal=GoalType.GATE, duration_minutes=30)
    tracker.log_session(goal=GoalType.DEV, duration_minutes=45)
    tracker.log_session(goal=GoalType.ENGLISH, duration_minutes=25)

    totals = tracker.get_total_minutes_by_goal()
    assert totals[GoalType.GATE] == 90
    assert totals[GoalType.DEV] == 45
    assert totals[GoalType.ENGLISH] == 25
    assert GoalType.SSC not in totals
    assert totals.get(GoalType.SSC, 0) == 0


def test_get_streak_days_empty():
    tracker = StudyTimeTracker()
    assert tracker.get_streak_days() == 0


def test_get_streak_days_single_session():
    tracker = StudyTimeTracker()
    tracker.log_session(
        goal=GoalType.GATE,
        duration_minutes=30,
        timestamp=datetime(2026, 11, 8, 10, 0, tzinfo=UTC),
    )
    assert tracker.get_streak_days() == 1


def test_get_streak_days_multiple_sessions_same_day():
    tracker = StudyTimeTracker()
    tracker.log_session(
        goal=GoalType.GATE,
        duration_minutes=30,
        timestamp=datetime(2026, 11, 8, 9, 0, tzinfo=UTC),
    )
    tracker.log_session(
        goal=GoalType.DEV,
        duration_minutes=60,
        timestamp=datetime(2026, 11, 8, 14, 0, tzinfo=UTC),
    )
    tracker.log_session(
        goal=GoalType.ENGLISH,
        duration_minutes=20,
        timestamp=datetime(2026, 11, 8, 20, 0, tzinfo=UTC),
    )
    assert tracker.get_streak_days() == 1


def test_get_streak_days_consecutive_days():
    tracker = StudyTimeTracker()
    base_date = datetime(2026, 11, 1, 10, 0, tzinfo=UTC)
    for day in range(5):
        tracker.log_session(
            goal=GoalType.GATE,
            duration_minutes=30,
            timestamp=base_date + timedelta(days=day),
        )
    assert tracker.get_streak_days() == 5


def test_get_streak_days_broken_streak():
    tracker = StudyTimeTracker()
    # Sessions on Day 1, Day 2, Day 3, gap on Day 4, session on Day 5, Day 6
    dates = [
        datetime(2026, 11, 1, 10, 0, tzinfo=UTC),
        datetime(2026, 11, 2, 10, 0, tzinfo=UTC),
        datetime(2026, 11, 3, 10, 0, tzinfo=UTC),
        # Gap on Nov 4
        datetime(2026, 11, 5, 10, 0, tzinfo=UTC),
        datetime(2026, 11, 6, 10, 0, tzinfo=UTC),
    ]
    for d in dates:
        tracker.log_session(goal=GoalType.GATE, duration_minutes=30, timestamp=d)

    # Current consecutive streak from Nov 6 should be 2 (Nov 5 and Nov 6)
    assert tracker.get_streak_days() == 2


def test_get_streak_days_with_reference_date():
    tracker = StudyTimeTracker()
    tracker.log_session(
        goal=GoalType.DEV,
        duration_minutes=30,
        timestamp=datetime(2026, 11, 1, 10, 0, tzinfo=UTC),
    )
    tracker.log_session(
        goal=GoalType.DEV,
        duration_minutes=30,
        timestamp=datetime(2026, 11, 2, 10, 0, tzinfo=UTC),
    )

    # Reference on same day as last session
    assert tracker.get_streak_days(reference_date=date(2026, 11, 2)) == 2
    # Reference on next day (yesterday was active, streak remains active)
    assert tracker.get_streak_days(reference_date=date(2026, 11, 3)) == 2
    # Reference two days later (streak broken)
    assert tracker.get_streak_days(reference_date=date(2026, 11, 4)) == 0
