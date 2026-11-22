from __future__ import annotations

from datetime import date, timedelta

import pytest

from techradar.planner.progress import (
    DayStat,
    WeekProgress,
    parse_week_id,
    render_review,
    run_weekly_review,
    sleep_accuracy_pattern,
    streak_from_days,
    week_bounds,
    week_id,
    week_progress,
)


def days(
    low: int,
    high: int,
    low_acc: float = 0.60,
    high_acc: float = 0.72,
) -> list[DayStat]:
    stats: list[DayStat] = []
    base = date(2026, 10, 1)
    for i in range(low):
        stats.append(
            DayStat(
                date=base + timedelta(days=i),
                sleep_band=2,
                quiz_accuracy=low_acc,
            )
        )
    for j in range(high):
        stats.append(
            DayStat(
                date=base + timedelta(days=low + j),
                sleep_band=4,
                quiz_accuracy=high_acc,
            )
        )
    return stats


def test_week_bounds_monday_to_sunday():
    assert week_bounds(date(2026, 11, 8)) == (date(2026, 11, 2), date(2026, 11, 8))
    assert week_bounds(date(2026, 11, 2)) == (date(2026, 11, 2), date(2026, 11, 8))
    assert week_bounds(date(2026, 11, 5)) == (date(2026, 11, 2), date(2026, 11, 8))


def test_pattern_needs_seven_days_each():
    assert sleep_accuracy_pattern(days(low=6, high=10)) is None
    assert sleep_accuracy_pattern(days(low=10, high=6)) is None


def test_pattern_difference_and_wording():
    p = sleep_accuracy_pattern(days(low=7, high=7, low_acc=0.60, high_acc=0.72))
    assert p is not None
    assert p.diff_points == pytest.approx(12.0)
    assert p.text.startswith("Your quiz accuracy is 12 points lower after nights under 6 hours")
    assert "(14 days of data)" in p.text


def test_pattern_higher_when_short_sleep_scores_better():
    p = sleep_accuracy_pattern(days(low=7, high=7, low_acc=0.80, high_acc=0.70))
    assert p is not None and "10 points higher" in p.text


def test_week_id_round_trip():
    assert week_id(date(2026, 11, 2)) == "2026-W45"
    assert parse_week_id("2026-W45") == date(2026, 11, 2)
    assert parse_week_id("2026-W99") is None
    assert parse_week_id("../etc") is None


def test_streak_counts_back_from_today_or_yesterday():
    active = {date(2026, 11, 5), date(2026, 11, 6), date(2026, 11, 7)}
    assert streak_from_days(active, date(2026, 11, 7)) == 3
    assert streak_from_days(active, date(2026, 11, 8)) == 3  # today not over yet
    assert streak_from_days(active, date(2026, 11, 9)) == 0
    assert streak_from_days(set(), date(2026, 11, 9)) == 0


def test_review_page_is_generated_and_names_every_goal():
    wp = WeekProgress(
        minutes_by_goal={"gate": 30},
        targets={"gate": 300, "dev": 600},
        streak_days=2,
    )
    page = render_review("2026-W45", wp)
    assert page.startswith("---\nkind: review\ngenerated: true\nweek: 2026-W45\n---\n")
    assert "- **GATE:** 30 / 300 min" in page and "- **DEV:** 0 / 600 min" in page


@pytest.mark.db
@pytest.mark.asyncio
async def test_week_progress_counts_the_india_week(session):
    from datetime import UTC, datetime

    from techradar.db.models import StudySession

    # 19:00 UTC on Sunday 8 Nov is 00:30 on Monday 9 Nov in India: next week
    session.add(
        StudySession(
            goal="gate",
            topic="in",
            started_at=datetime(2026, 11, 7, 10, 0, tzinfo=UTC),
            ended_at=datetime(2026, 11, 7, 11, 0, tzinfo=UTC),
            minutes=60,
        )
    )
    session.add(
        StudySession(
            goal="gate",
            topic="out",
            started_at=datetime(2026, 11, 8, 19, 0, tzinfo=UTC),
            ended_at=datetime(2026, 11, 8, 20, 0, tzinfo=UTC),
            minutes=40,
        )
    )
    await session.flush()
    wp = await week_progress(session, date(2026, 11, 2))
    assert wp.minutes_by_goal == {"gate": 60}
    assert wp.pattern is None


@pytest.mark.db
@pytest.mark.asyncio
async def test_weekly_review_sends_once_and_writes_the_page(session, tmp_path):
    from sqlalchemy import select

    from techradar.db.models import Outbox

    first = await run_weekly_review(
        session, date(2026, 11, 8), owner_chat_id=4242, vault_root=tmp_path
    )
    assert first is not None
    assert (tmp_path / "reviews" / "2026-W45.md").read_text() == first
    assert await run_weekly_review(session, date(2026, 11, 8), owner_chat_id=4242) is None
    rows = (
        await session.execute(select(Outbox).where(Outbox.purpose == "weekly_review"))
    ).scalars()
    assert len([m for m in rows if m.chat_id == 4242]) == 1
