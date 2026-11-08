from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta

from pydantic import BaseModel, Field


def week_bounds(any_day: date) -> tuple[date, date]:
    """Calculate the Monday-to-Sunday week boundary for any given date.

    Monday is day 0, Sunday is day 6.
    """
    weekday = any_day.weekday()
    monday = any_day - timedelta(days=weekday)
    sunday = monday + timedelta(days=6)
    return monday, sunday


class DayStat(BaseModel):
    """Daily check-in and quiz statistics."""

    date: date
    sleep_band: int = Field(ge=1, le=5)  # 1: <5h, 2: 5-6h, 3: 6-7h, 4: 7-8h, 5: >8h
    quiz_accuracy: float | None = Field(default=None, ge=0.0, le=1.0)


class Pattern(BaseModel):
    """Behavioral and performance correlation pattern."""

    text: str
    days_low: int
    days_high: int
    diff_points: float


def sleep_accuracy_pattern(days: Sequence[DayStat]) -> Pattern | None:
    """Analyze correlation between sleep duration and quiz accuracy.

    Low sleep group: sleep_band <= 2 (<6 hours)
    High sleep group: sleep_band >= 3 (>=6 hours)
    Requires at least 7 days with quiz results in each group.
    """
    low_group = [d for d in days if d.sleep_band <= 2 and d.quiz_accuracy is not None]
    high_group = [d for d in days if d.sleep_band >= 3 and d.quiz_accuracy is not None]

    if len(low_group) < 7 or len(high_group) < 7:
        return None

    low_scores = [d.quiz_accuracy for d in low_group if d.quiz_accuracy is not None]
    high_scores = [d.quiz_accuracy for d in high_group if d.quiz_accuracy is not None]
    low_avg = sum(low_scores) / len(low_group)
    high_avg = sum(high_scores) / len(high_group)

    diff_points = abs(high_avg - low_avg) * 100.0
    total_days = len(low_group) + len(high_group)

    if low_avg < high_avg:
        text = (
            f"Your quiz accuracy is {diff_points:.0f} points lower after nights "
            f"under 6 hours ({total_days} days of data)."
        )
    else:
        text = (
            f"Your quiz accuracy is {diff_points:.0f} points higher after nights "
            f"under 6 hours ({total_days} days of data)."
        )

    return Pattern(
        text=text,
        days_low=len(low_group),
        days_high=len(high_group),
        diff_points=diff_points,
    )


class WeekProgress(BaseModel):
    """Weekly study summary with progress against targets."""

    minutes_by_goal: dict[str, int] = Field(default_factory=dict)
    targets: dict[str, int] = Field(default_factory=dict)
    streak_days: int = Field(ge=0, default=0)
    quiz_accuracy: float | None = Field(default=None, ge=0.0, le=1.0)
    cards_reviewed: int = Field(ge=0, default=0)
    pattern: Pattern | None = None


def compute_week_progress(
    minutes_by_goal: dict[str, int],
    targets: dict[str, int],
    streak_days: int,
    quiz_accuracy: float | None,
    cards_reviewed: int,
    day_stats: Sequence[DayStat] | None = None,
) -> WeekProgress:
    """Compute aggregate progress for the current week."""
    pattern = sleep_accuracy_pattern(day_stats) if day_stats else None
    return WeekProgress(
        minutes_by_goal=minutes_by_goal,
        targets=targets,
        streak_days=streak_days,
        quiz_accuracy=quiz_accuracy,
        cards_reviewed=cards_reviewed,
        pattern=pattern,
    )
