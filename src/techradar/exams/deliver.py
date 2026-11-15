from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import DrillAttempt
from techradar.exams.drills import daily_set


class DrillOutcome(BaseModel):
    already_answered: bool = False
    correct: bool
    explanation: str
    seconds: float
    chosen: str
    answer_option: str


async def record_drill(
    session: AsyncSession,
    day: date,
    n: int,
    chosen: int,
    sent_at: datetime,
    now: datetime,
) -> DrillOutcome:
    """Record an answer to question n of day's drill set. Idempotent per (day, n)."""
    items = daily_set(day)
    if n < 0 or n >= len(items):
        raise ValueError(f"Question index {n} out of range for daily set (size {len(items)})")

    item = items[n]

    # Check for existing attempt for (day, n)
    stmt = select(DrillAttempt).where(DrillAttempt.day == day)
    res = await session.execute(stmt)
    attempts = list(res.scalars().all())

    existing: DrillAttempt | None = None
    for a in attempts:
        if isinstance(a.item, dict) and a.item.get("n") == n:
            existing = a
            break

    if existing is not None:
        item_data = existing.item if isinstance(existing.item, dict) else {}
        options = item_data.get("options", item.options)
        ans_idx = item_data.get("answer_index", item.answer_index)
        correct_opt = options[ans_idx] if 0 <= ans_idx < len(options) else ""
        return DrillOutcome(
            already_answered=True,
            correct=existing.correct,
            explanation=str(item_data.get("explanation", item.explanation)),
            seconds=existing.seconds,
            chosen=existing.chosen,
            answer_option=correct_opt,
        )

    seconds = max(0.0, (now - sent_at).total_seconds())
    correct = chosen == item.answer_index
    chosen_str = item.options[chosen] if 0 <= chosen < len(item.options) else str(chosen)

    item_dict = item.model_dump()
    item_dict["n"] = n

    attempt = DrillAttempt(
        day=day,
        kind=item.kind,
        item=item_dict,
        chosen=chosen_str,
        correct=correct,
        seconds=seconds,
        at=now,
    )
    session.add(attempt)
    await session.flush()

    return DrillOutcome(
        already_answered=False,
        correct=correct,
        explanation=item.explanation,
        seconds=seconds,
        chosen=chosen_str,
        answer_option=item.options[item.answer_index],
    )


def render_drill_summary(attempts: Sequence[DrillAttempt]) -> str:
    """Render summary text for a series of drill attempts."""
    if not attempts:
        return "Aptitude: 0/0 · avg 0.0 s per question · slowest: none"

    total = len(attempts)
    correct_count = sum(1 for a in attempts if a.correct)
    total_seconds = sum(a.seconds for a in attempts)
    avg_s = total_seconds / total

    slowest = max(attempts, key=lambda a: a.seconds)
    slowest_kind = slowest.kind

    return (
        f"Aptitude: {correct_count}/{total} · avg {avg_s:.1f} s per question"
        f" · slowest: {slowest_kind}"
    )
