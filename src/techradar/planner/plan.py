from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import MCQ, Flashcard, Plan, QuizAttempt, Revision
from techradar.exams.final30 import final_30
from techradar.planner.sessions import Goal, local_date, minutes_by_goal


@dataclass(frozen=True)
class RevisionRow:
    """A revision that is due: what `compose_plan` needs to name a topic."""

    goal: Goal
    topic: str
    due_date: date | None = None


DEFAULT_EXAM_PRIORITY = [Goal.GOV, Goal.GATE]
DEFAULT_WEEKLY_TARGETS: dict[Goal, int] = {
    Goal.DEV: 600,
    Goal.GATE: 300,
    Goal.GOV: 420,
    Goal.CURRENT: 105,
    Goal.ENGLISH: 140,
}


def compose_plan(
    today: date,
    *,
    due_revisions: Sequence[RevisionRow],
    due_cards: int,
    quiz_ready: bool,
    minutes_this_week: Mapping[Goal, int],
    targets: Mapping[Goal, int],
    priority: Sequence[Goal],
    final_30_exam: str | None = None,
) -> list[str]:
    """Compose daily morning plan lines in strict priority order."""
    lines: list[str] = []

    # 1. Final 30 days exam alert
    if final_30_exam:
        lines.append(f"⏳ Final 30 days: {final_30_exam}")

    # 2. Daily Radar intake
    lines.append("📰 Radar (10–15 min)")

    # 3. Current affairs quiz
    if quiz_ready:
        lines.append("📝 Current affairs quiz: 10 MCQs")

    # 4. Spaced reviews due
    review_parts: list[str] = []
    if due_cards > 0:
        review_parts.append(f"{due_cards} flashcards")
    if len(due_revisions) > 0:
        review_parts.append(f"{len(due_revisions)} topic revisions")
    if review_parts:
        lines.append(f"🔁 Reviews due: {' + '.join(review_parts)}")

    # 5. Goal session with highest deficit
    # Determine candidate goals from priority (fallback to all target goals if priority empty)
    candidate_goals = list(priority) if priority else list(targets.keys())

    priority_map = {g: idx for idx, g in enumerate(priority)}

    def _deficit_score(g: Goal) -> tuple[float, int]:
        done = minutes_this_week.get(g, 0)
        tgt = targets.get(g, 1)
        deficit = 1.0 - (done / max(tgt, 1))
        # Round to 4 decimal places to prevent float precision noise on equal deficits
        rounded_deficit = round(deficit, 4)
        p_idx = priority_map.get(g, 999)
        return (-rounded_deficit, p_idx)

    chosen_goal = min(candidate_goals, key=_deficit_score)

    # Find first due revision topic for chosen goal
    first_topic = "next topic"
    for r in due_revisions:
        r_goal = getattr(r, "goal", None)
        if r_goal == chosen_goal.value or r_goal == chosen_goal:
            first_topic = getattr(r, "topic", "next topic")
            break

    goal_name = chosen_goal.name
    if final_30_exam:
        topic_str = first_topic if first_topic != "next topic" else "weak areas"
        lines.append(f"🎓 {goal_name}: revise {topic_str} (45 min)")
    else:
        lines.append(f"🎓 {goal_name}: {first_topic} (45 min)")

    # 6. English practice
    lines.append("🔤 English: 5 new words + 10 grammar questions")

    return lines


QUIZ_SIZE = 10


async def plan_for_today(
    session: AsyncSession,
    now: datetime,
    *,
    targets: Mapping[Goal, int] | None = None,
    priority: Sequence[Goal] | None = None,
    exam_dates: Mapping[str, date] | None = None,
) -> list[str]:
    """Read today's facts from Postgres, compose the plan lines and store them in `plans`.

    WIRING(claude): the briefing job calls this before `run_briefing` and passes the result as
    `plan_lines`. Revisions that fell due while the server was off are still due, so a 30-hour
    gap shows them in the next plan (no duplicates: one row per date).
    """
    today = local_date(now)
    week_start = today - timedelta(days=today.weekday())

    revs = (
        (
            await session.execute(
                select(Revision)
                .where(Revision.done_at.is_(None), Revision.due_date <= today)
                .order_by(Revision.due_date, Revision.id)
            )
        )
        .scalars()
        .all()
    )
    due_revisions = [RevisionRow(Goal(r.goal), r.topic, r.due_date) for r in revs]

    due_cards = int(
        (
            await session.execute(
                select(func.count(Flashcard.id)).where(
                    Flashcard.retired.is_(False), Flashcard.due <= now
                )
            )
        ).scalar_one()
    )
    unseen_mcqs = int(
        (
            await session.execute(
                select(func.count(MCQ.id)).where(
                    MCQ.status == "active",
                    MCQ.id.not_in(select(QuizAttempt.mcq_id)),
                )
            )
        ).scalar_one()
    )

    lines = compose_plan(
        today,
        due_revisions=due_revisions,
        due_cards=due_cards,
        quiz_ready=unseen_mcqs >= QUIZ_SIZE,
        minutes_this_week=await minutes_by_goal(session, week_start, today),
        targets=targets or DEFAULT_WEEKLY_TARGETS,
        priority=priority or DEFAULT_EXAM_PRIORITY,
        final_30_exam=final_30(exam_dates or {}, today),
    )
    await session.merge(Plan(date=today, lines=lines))
    await session.flush()
    return lines
