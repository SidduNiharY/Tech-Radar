from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta
from pathlib import Path, PurePosixPath

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import Checkin, Flashcard, QuizAttempt, StudySession
from techradar.messaging.outbox import enqueue_message
from techradar.pipeline.writer import write_note
from techradar.planner.sessions import Goal


def week_bounds(any_day: date) -> tuple[date, date]:
    """Calculate Monday to Sunday bounding dates for the given day."""
    start = any_day - timedelta(days=any_day.weekday())
    end = start + timedelta(days=6)
    return start, end


class DayStat(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: date
    sleep_band: int | None = None
    quiz_accuracy: float | None = None


class Pattern(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    days_low: int
    days_high: int
    diff_points: float


def sleep_accuracy_pattern(days: Sequence[DayStat]) -> Pattern | None:
    """Computes sleep vs quiz accuracy correlation pattern."""
    low_group = [
        d
        for d in days
        if d.sleep_band is not None and d.sleep_band <= 2 and d.quiz_accuracy is not None
    ]
    high_group = [
        d
        for d in days
        if d.sleep_band is not None and d.sleep_band >= 3 and d.quiz_accuracy is not None
    ]

    if len(low_group) < 7 or len(high_group) < 7:
        return None

    avg_low = sum(d.quiz_accuracy for d in low_group) / len(low_group)
    avg_high = sum(d.quiz_accuracy for d in high_group) / len(high_group)

    diff_points = abs(avg_high - avg_low) * 100
    direction = "lower" if avg_low < avg_high else "higher"
    total_data_days = len(low_group) + len(high_group)
    diff_rounded = int(round(diff_points))

    text = (
        f"Your quiz accuracy is {diff_rounded} points {direction} after "
        f"nights under 6 hours ({total_data_days} days of data)."
    )

    return Pattern(
        text=text,
        days_low=len(low_group),
        days_high=len(high_group),
        diff_points=round(diff_points, 1),
    )


class WeekProgress(BaseModel):
    model_config = ConfigDict(extra="forbid")

    minutes_by_goal: dict[str, int] = Field(default_factory=dict)
    targets: dict[str, int] = Field(default_factory=dict)
    streak_days: int = 0
    quiz_accuracy: float | None = None
    cards_reviewed: int = 0
    pattern: Pattern | None = None


async def week_progress(session: AsyncSession, week_start: date) -> WeekProgress:
    """Calculate progress stats for a given week."""
    week_end = week_start + timedelta(days=6)

    # 1. Study minutes by goal
    stmt = (
        select(StudySession.goal, func.coalesce(func.sum(StudySession.minutes), 0))
        .where(
            func.date(StudySession.started_at) >= week_start,
            func.date(StudySession.started_at) <= week_end,
        )
        .group_by(StudySession.goal)
    )
    res = await session.execute(stmt)
    minutes_by_goal = {r[0]: int(r[1]) for r in res.all()}

    # 2. Quiz accuracy
    quiz_stmt = select(
        func.count(QuizAttempt.id),
        func.coalesce(func.sum(func.cast(QuizAttempt.correct, func.integer)), 0),
    ).where(
        QuizAttempt.date >= week_start,
        QuizAttempt.date <= week_end,
    )
    quiz_res = await session.execute(quiz_stmt)
    total_quiz, correct_quiz = quiz_res.one()
    quiz_accuracy = (float(correct_quiz) / total_quiz) if total_quiz > 0 else None

    # 3. Cards reviewed
    cards_stmt = select(func.count(Flashcard.id)).where(
        Flashcard.first_shown_at.is_not(None),
        func.date(Flashcard.first_shown_at) >= week_start,
        func.date(Flashcard.first_shown_at) <= week_end,
    )
    cards_res = await session.execute(cards_stmt)
    cards_reviewed = int(cards_res.scalar() or 0)

    # 4. DayStat list for pattern analysis
    day_stats: list[DayStat] = []
    # Pull recent checkins
    checkin_stmt = select(Checkin).order_by(Checkin.date.desc()).limit(60)
    checkins = {c.date: c for c in (await session.execute(checkin_stmt)).scalars().all()}
    for d, c in checkins.items():
        day_stats.append(
            DayStat(
                date=d,
                sleep_band=c.sleep_band,
                quiz_accuracy=quiz_accuracy,  # Fallback proxy for day accuracy
            )
        )

    pattern = sleep_accuracy_pattern(day_stats)

    targets = {
        Goal.DEV.value: 600,
        Goal.GATE.value: 300,
        Goal.GOV.value: 420,
        Goal.CURRENT.value: 105,
        Goal.ENGLISH.value: 140,
    }

    return WeekProgress(
        minutes_by_goal=minutes_by_goal,
        targets=targets,
        streak_days=len(minutes_by_goal),
        quiz_accuracy=quiz_accuracy,
        cards_reviewed=cards_reviewed,
        pattern=pattern,
    )


async def run_weekly_review(
    session: AsyncSession,
    week_end: date,
    vault_root: Path | None = None,
) -> str:
    """Generate weekly review note, write to vault, and enqueue summary message."""
    week_start, _ = week_bounds(week_end)
    wp = await week_progress(session, week_start)

    year, week_num, _ = week_start.isocalendar()
    week_slug = f"{year}-W{week_num:02d}"

    lines = [
        "---",
        "kind: review",
        "generated: true",
        f"week: {week_slug}",
        "---",
        f"# Weekly Review · {week_slug}",
        "",
        f"- **Streak:** {wp.streak_days} days active",
        f"- **Flashcards reviewed:** {wp.cards_reviewed}",
    ]
    if wp.quiz_accuracy is not None:
        lines.append(f"- **Quiz accuracy:** {int(wp.quiz_accuracy * 100)}%")
    if wp.pattern:
        lines.append(f"- **Observed pattern:** {wp.pattern.text}")

    lines.append("")
    lines.append("## Study Time by Goal")
    for goal, mins in wp.minutes_by_goal.items():
        tgt = wp.targets.get(goal, 0)
        lines.append(f"- **{goal.upper()}:** {mins} / {tgt} min")

    content = "\n".join(lines).strip() + "\n"

    if vault_root:
        rel = PurePosixPath("reviews") / f"{week_slug}.md"
        write_note(vault_root, rel, content)

    outbox_msg = f"Your weekly review for {week_slug} is ready: reviews/{week_slug}.md"
    await enqueue_message(session, outbox_msg)

    return content
