from __future__ import annotations

from datetime import date, timedelta

import pytest

from techradar.planner.progress import (
    DayStat,
    sleep_accuracy_pattern,
    week_bounds,
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
