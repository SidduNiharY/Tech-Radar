from __future__ import annotations

from datetime import date

import pytest

from techradar.planner.progress import (
    DayStat,
    Pattern,
    WeekProgress,
    compute_week_progress,
    sleep_accuracy_pattern,
    week_bounds,
)


def make_day_stats(
    low: int,
    high: int,
    low_acc: float = 0.60,
    high_acc: float = 0.72,
) -> list[DayStat]:
    stats: list[DayStat] = []
    # low sleep days (band <= 2)
    for i in range(low):
        stats.append(
            DayStat(
                date=date(2026, 10, 1 + (i % 28)),
                sleep_band=2,
                quiz_accuracy=low_acc,
            )
        )
    # high sleep days (band >= 3)
    for i in range(high):
        stats.append(
            DayStat(
                date=date(2026, 10, 15 + (i % 15)),
                sleep_band=4,
                quiz_accuracy=high_acc,
            )
        )
    return stats


def test_week_bounds_monday_to_sunday():
    # 2026-11-08 was a Sunday -> Monday 2026-11-02 to Sunday 2026-11-08
    assert week_bounds(date(2026, 11, 8)) == (date(2026, 11, 2), date(2026, 11, 8))
    # 2026-11-04 was a Wednesday -> same bounds
    assert week_bounds(date(2026, 11, 4)) == (date(2026, 11, 2), date(2026, 11, 8))
    # 2026-11-02 was Monday
    assert week_bounds(date(2026, 11, 2)) == (date(2026, 11, 2), date(2026, 11, 8))


def test_pattern_needs_seven_days_each():
    # 6 low days and 10 high days -> not enough in low group
    days = make_day_stats(low=6, high=10)
    assert sleep_accuracy_pattern(days) is None

    # 10 low days and 6 high days -> not enough in high group
    days = make_day_stats(low=10, high=6)
    assert sleep_accuracy_pattern(days) is None


def test_pattern_difference_and_wording():
    days = make_day_stats(low=7, high=7, low_acc=0.60, high_acc=0.72)
    p = sleep_accuracy_pattern(days)
    assert p is not None
    assert isinstance(p, Pattern)
    assert p.days_low == 7
    assert p.days_high == 7
    assert p.diff_points == pytest.approx(12.0)
    assert p.text.startswith("Your quiz accuracy is 12 points lower after nights under 6 hours")
    assert "(14 days of data)" in p.text


def test_pattern_higher_when_low_sleep_has_better_accuracy():
    days = make_day_stats(low=7, high=7, low_acc=0.85, high_acc=0.70)
    p = sleep_accuracy_pattern(days)
    assert p is not None
    assert p.diff_points == pytest.approx(15.0)
    assert p.text.startswith("Your quiz accuracy is 15 points higher after nights under 6 hours")


def test_compute_week_progress():
    progress = compute_week_progress(
        minutes_by_goal={"gate": 180, "dev": 120, "english": 60},
        targets={"gate": 300, "dev": 150, "english": 90},
        streak_days=5,
        quiz_accuracy=0.82,
        cards_reviewed=45,
        day_stats=make_day_stats(low=7, high=7, low_acc=0.65, high_acc=0.75),
    )
    assert isinstance(progress, WeekProgress)
    assert progress.streak_days == 5
    assert progress.quiz_accuracy == pytest.approx(0.82)
    assert progress.cards_reviewed == 45
    assert progress.minutes_by_goal["gate"] == 180
    assert progress.pattern is not None
    assert progress.pattern.diff_points == pytest.approx(10.0)
