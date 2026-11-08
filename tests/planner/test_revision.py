from __future__ import annotations

from datetime import date, timedelta

from techradar.planner.revision import (
    REVISION_OFFSETS,
    RevisionCalendar,
    RevisionCheckpoint,
)
from techradar.planner.schedule import StudyGoal


def test_revision_offsets_constant():
    assert REVISION_OFFSETS == [1, 7, 30, 90]


def test_schedule_topic_revisions_offsets():
    learned = date(2026, 11, 8)
    checkpoints = RevisionCalendar.schedule_topic_revisions(
        topic_id="os-virtual-memory",
        topic_title="Virtual Memory & Paging",
        goal=StudyGoal.GATE,
        learned_date=learned,
    )

    assert len(checkpoints) == 4
    assert [cp.stage for cp in checkpoints] == [1, 2, 3, 4]
    assert [cp.due_date for cp in checkpoints] == [
        learned + timedelta(days=1),
        learned + timedelta(days=7),
        learned + timedelta(days=30),
        learned + timedelta(days=90),
    ]

    # Exact expected dates:
    assert checkpoints[0].due_date == date(2026, 11, 9)
    assert checkpoints[1].due_date == date(2026, 11, 15)
    assert checkpoints[2].due_date == date(2026, 12, 8)
    assert checkpoints[3].due_date == date(2027, 2, 6)

    # Check model attributes:
    for cp in checkpoints:
        assert isinstance(cp, RevisionCheckpoint)
        assert cp.topic_id == "os-virtual-memory"
        assert cp.topic_title == "Virtual Memory & Paging"
        assert cp.goal == StudyGoal.GATE


def test_revision_calendar_instance_and_class_calls():
    learned = date(2026, 11, 8)
    cal = RevisionCalendar()

    # Call on instance
    cps_instance = cal.schedule_topic_revisions(
        topic_id="py-asyncio",
        topic_title="AsyncIO Event Loop",
        goal=StudyGoal.DEV,
        learned_date=learned,
    )
    # Call on class
    cps_class = RevisionCalendar.schedule_topic_revisions(
        topic_id="py-asyncio",
        topic_title="AsyncIO Event Loop",
        goal=StudyGoal.DEV,
        learned_date=learned,
    )

    assert len(cps_instance) == 4
    assert cps_instance == cps_class


def test_get_due_revisions_filtering():
    learned = date(2026, 11, 8)
    checkpoints = RevisionCalendar.schedule_topic_revisions(
        topic_id="gk-polity",
        topic_title="Indian Constitution Preamble",
        goal=StudyGoal.SSC,
        learned_date=learned,
    )

    # Before first revision (+1 day -> 2026-11-09)
    due_0 = RevisionCalendar.get_due_revisions(checkpoints, target_date=date(2026, 11, 8))
    assert due_0 == []

    # Exactly at +1 day (2026-11-09)
    due_1 = RevisionCalendar.get_due_revisions(checkpoints, target_date=date(2026, 11, 9))
    assert [cp.stage for cp in due_1] == [1]

    # At +7 days (2026-11-15) -> stages 1 and 2
    due_2 = RevisionCalendar.get_due_revisions(checkpoints, target_date=date(2026, 11, 15))
    assert [cp.stage for cp in due_2] == [1, 2]

    # Between stage 2 and stage 3 (e.g. 2026-11-20) -> stages 1 and 2
    due_mid = RevisionCalendar.get_due_revisions(checkpoints, target_date=date(2026, 11, 20))
    assert [cp.stage for cp in due_mid] == [1, 2]

    # At +30 days (2026-12-08) -> stages 1, 2, and 3
    due_3 = RevisionCalendar.get_due_revisions(checkpoints, target_date=date(2026, 12, 8))
    assert [cp.stage for cp in due_3] == [1, 2, 3]

    # At +90 days (2027-02-06) -> all 4 stages
    due_4 = RevisionCalendar.get_due_revisions(checkpoints, target_date=date(2027, 2, 6))
    assert [cp.stage for cp in due_4] == [1, 2, 3, 4]

    # Past +90 days (2027-03-01) -> all 4 stages
    due_past = RevisionCalendar.get_due_revisions(checkpoints, target_date=date(2027, 3, 1))
    assert [cp.stage for cp in due_past] == [1, 2, 3, 4]


def test_get_due_revisions_multiple_topics():
    cp_topic1 = RevisionCalendar.schedule_topic_revisions(
        topic_id="t1",
        topic_title="Topic 1",
        goal=StudyGoal.BANKING,
        learned_date=date(2026, 11, 1),
    )
    cp_topic2 = RevisionCalendar.schedule_topic_revisions(
        topic_id="t2",
        topic_title="Topic 2",
        goal=StudyGoal.ENGLISH,
        learned_date=date(2026, 11, 7),
    )

    combined = cp_topic1 + cp_topic2
    # On 2026-11-08:
    # Topic 1 (learned Nov 1): +1 (Nov 2) and +7 (Nov 8) are due.
    # Topic 2 (learned Nov 7): +1 (Nov 8) is due.
    due = RevisionCalendar.get_due_revisions(combined, target_date=date(2026, 11, 8))
    assert len(due) == 3
    assert {cp.topic_id for cp in due} == {"t1", "t2"}
