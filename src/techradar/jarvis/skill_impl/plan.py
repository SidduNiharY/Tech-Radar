"""Plan skill, read side: the day's plan lines, numbered."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import Plan
from techradar.jarvis.skill_impl.result import SkillReply


def resolve_day(now: datetime, day: str | date | None) -> date:
    today = now.date()
    if day is None or day == "today":
        return today
    if day == "tomorrow":
        return today + timedelta(days=1)
    if isinstance(day, date):
        return day
    raise ValueError(f"unknown day: {day!r}")


async def run(session: AsyncSession, now: datetime, *, day: str | date | None = None) -> SkillReply:
    """`plan read`. Adding, moving and removing lines are writes: they come with tickets."""
    d = resolve_day(now, day)
    row = await session.get(Plan, d)
    lines = [str(x) for x in (row.lines if row else [])]
    label = "today" if d == now.date() else f"{d.day} {d.strftime('%b')}"
    if not lines:
        return SkillReply(say=f"Nothing is planned for {label}.", list_len=0)
    numbered = " ".join(f"{i}. {line}" for i, line in enumerate(lines[:15], 1))
    return SkillReply(say=f"Your plan for {label}: {numbered}", list_len=min(len(lines), 15))
