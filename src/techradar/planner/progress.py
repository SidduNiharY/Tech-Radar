from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import date, datetime, timedelta
from pathlib import Path, PurePosixPath

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Integer, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import Checkin, Flashcard, Outbox, QuizAttempt, StudySession
from techradar.messaging.outbox import enqueue_message
from techradar.pipeline.writer import write_note
from techradar.planner.plan import DEFAULT_WEEKLY_TARGETS
from techradar.planner.sessions import IST, Goal, local_date, local_day_bounds, minutes_by_goal

WEEK_ID = re.compile(r"^(\d{4})-W(\d{2})$")
PATTERN_WINDOW_DAYS = 60
WEEKLY_REVIEW_PURPOSE = "weekly_review"


def week_bounds(any_day: date) -> tuple[date, date]:
    """Calculate Monday to Sunday bounding dates for the given day."""
    start = any_day - timedelta(days=any_day.weekday())
    end = start + timedelta(days=6)
    return start, end


def week_id(week_start: date) -> str:
    """`2026-W45` for the ISO week that starts on `week_start`."""
    year, week, _ = week_start.isocalendar()
    return f"{year}-W{week:02d}"


def parse_week_id(value: str) -> date | None:
    """Monday of `YYYY-Www` (for `GET /v1/progress?week=`), or None when it is not a week."""
    m = WEEK_ID.match(value)
    if m is None:
        return None
    try:
        return date.fromisocalendar(int(m.group(1)), int(m.group(2)), 1)
    except ValueError:
        return None


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
    """Computes sleep vs quiz accuracy correlation pattern.

    Worded as a pattern, never as a cause; needs 7 days with a quiz in each group.
    """
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


def streak_from_days(active: set[date], as_of: date) -> int:
    """Consecutive study days ending `as_of` (or the day before, while `as_of` is still open)."""
    day = as_of if as_of in active else as_of - timedelta(days=1)
    streak = 0
    while day in active:
        streak += 1
        day -= timedelta(days=1)
    return streak


class WeekProgress(BaseModel):
    model_config = ConfigDict(extra="forbid")

    minutes_by_goal: dict[str, int] = Field(default_factory=dict)
    targets: dict[str, int] = Field(default_factory=dict)
    streak_days: int = 0
    quiz_accuracy: float | None = None
    cards_reviewed: int = 0
    pattern: Pattern | None = None


async def week_progress(
    session: AsyncSession,
    week_start: date,
    *,
    targets: Mapping[Goal, int] | None = None,
) -> WeekProgress:
    """Calculate progress stats for the week that starts on `week_start` (an India Monday).

    WIRING(claude): `GET /v1/progress?week=YYYY-Www` (the API agent) turns the query with
    `parse_week_id` (None means 422; no week means this week's Monday) and returns this model.
    """
    week_end = week_start + timedelta(days=6)
    start_ts, end_ts = local_day_bounds(week_start, week_end)

    minutes = await minutes_by_goal(session, week_start, week_end)

    # Quiz accuracy of the week
    total_quiz, correct_quiz = (
        await session.execute(
            select(
                func.count(QuizAttempt.id),
                func.coalesce(func.sum(cast(QuizAttempt.correct, Integer)), 0),
            ).where(QuizAttempt.date >= week_start, QuizAttempt.date <= week_end)
        )
    ).one()
    quiz_accuracy = (float(correct_quiz) / total_quiz) if total_quiz > 0 else None

    # Cards first shown this week (there is no per-review log; this is the nearest proxy)
    cards_reviewed = int(
        (
            await session.execute(
                select(func.count(Flashcard.id)).where(
                    Flashcard.first_shown_at >= start_ts, Flashcard.first_shown_at < end_ts
                )
            )
        ).scalar()
        or 0
    )

    # Streak: India days with a study session, up to the end of this week (or today)
    as_of = min(week_end, local_date(datetime.now(IST)))
    since_ts, _ = local_day_bounds(as_of - timedelta(days=PATTERN_WINDOW_DAYS), as_of)
    started = (
        (
            await session.execute(
                select(StudySession.started_at).where(StudySession.started_at >= since_ts)
            )
        )
        .scalars()
        .all()
    )
    streak = streak_from_days({local_date(s) for s in started}, as_of)

    # Pattern: each check-in day with that day's own quiz accuracy
    first = as_of - timedelta(days=PATTERN_WINDOW_DAYS)
    per_day = {
        d: (int(n), int(ok))
        for d, n, ok in (
            await session.execute(
                select(
                    QuizAttempt.date,
                    func.count(QuizAttempt.id),
                    func.coalesce(func.sum(cast(QuizAttempt.correct, Integer)), 0),
                )
                .where(QuizAttempt.date >= first, QuizAttempt.date <= as_of)
                .group_by(QuizAttempt.date)
            )
        ).all()
    }
    checkins = (
        (await session.execute(select(Checkin).where(Checkin.date >= first, Checkin.date <= as_of)))
        .scalars()
        .all()
    )
    day_stats = [
        DayStat(
            date=c.date,
            sleep_band=c.sleep_band,
            quiz_accuracy=(per_day[c.date][1] / per_day[c.date][0]) if c.date in per_day else None,
        )
        for c in checkins
    ]

    goal_targets = targets or DEFAULT_WEEKLY_TARGETS
    return WeekProgress(
        minutes_by_goal={g.value: m for g, m in minutes.items()},
        targets={g.value: t for g, t in goal_targets.items()},
        streak_days=streak,
        quiz_accuracy=quiz_accuracy,
        cards_reviewed=cards_reviewed,
        pattern=sleep_accuracy_pattern(day_stats),
    )


def render_review(week_slug: str, wp: WeekProgress) -> str:
    """The vault page for one week (`generated: true`)."""
    lines = [
        "---",
        "kind: review",
        "generated: true",
        f"week: {week_slug}",
        "---",
        f"# Weekly Review · {week_slug}",
        "",
        f"- **Streak:** {wp.streak_days} days",
        f"- **Flashcards shown:** {wp.cards_reviewed}",
    ]
    if wp.quiz_accuracy is not None:
        lines.append(f"- **Quiz accuracy:** {int(wp.quiz_accuracy * 100)}%")
    if wp.pattern:
        lines.append(f"- **Observed pattern:** {wp.pattern.text}")

    lines.append("")
    lines.append("## Study Time by Goal")
    for goal, target in wp.targets.items():
        lines.append(f"- **{goal.upper()}:** {wp.minutes_by_goal.get(goal, 0)} / {target} min")
    return "\n".join(lines).strip() + "\n"


async def run_weekly_review(
    session: AsyncSession,
    week_end: date,
    *,
    owner_chat_id: int,
    vault_root: Path | None = None,
    targets: Mapping[Goal, int] | None = None,
) -> str | None:
    """Write the review page and enqueue the summary; once per week.

    Returns the page text, or None when this week was already reviewed (a retry, or a
    catch-up run after downtime, sends nothing twice).
    """
    week_start, _ = week_bounds(week_end)
    week_slug = week_id(week_start)
    year, week, _ = week_start.isocalendar()
    ref = year * 100 + week

    already = await session.execute(
        select(Outbox.id)
        .where(
            Outbox.purpose == WEEKLY_REVIEW_PURPOSE,
            Outbox.ref_id == ref,
            Outbox.chat_id == owner_chat_id,
        )
        .limit(1)
    )
    if already.scalar_one_or_none() is not None:
        return None

    wp = await week_progress(session, week_start, targets=targets)
    content = render_review(week_slug, wp)

    if vault_root:
        write_note(vault_root, PurePosixPath("reviews") / f"{week_slug}.md", content)

    summary = [f"Your weekly review for {week_slug} is ready: reviews/{week_slug}.md"]
    done = sum(wp.minutes_by_goal.values())
    summary.append(f"{done} min studied, {wp.streak_days}-day streak.")
    if wp.pattern:
        summary.append(wp.pattern.text)
    await enqueue_message(
        session,
        chat_id=owner_chat_id,
        text="\n".join(summary),
        purpose=WEEKLY_REVIEW_PURPOSE,
        ref_id=ref,
    )
    return content
