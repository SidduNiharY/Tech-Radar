"""News skill: today's briefing stories, read from `briefings.items`."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import Briefing
from techradar.jarvis.skill_impl.result import SkillReply

LIST_MAX = 3
ASK_MORE = "Which one do you want to know more about?"
NO_BRIEFING = "There is no briefing for today yet."


async def run(
    session: AsyncSession,
    now: datetime,
    *,
    section: str | None = None,
    item: int | None = None,
) -> SkillReply:
    """Up to 3 stories (of one section, if given), or the details of story number `item`.

    `now` is the owner's local time, so its date is the briefing's date.
    """
    row = (
        await session.execute(select(Briefing).where(Briefing.date == now.date()))
    ).scalar_one_or_none()
    stories = [s for s in (row.items or []) if isinstance(s, dict)] if row else []
    if section is not None:
        stories = [s for s in stories if s.get("section") == section]
    if not stories:
        return SkillReply(say=NO_BRIEFING if row is None else "There is nothing in that section.")

    if item is not None:
        if not 1 <= item <= len(stories):
            return SkillReply(say=f"There is no story number {item}.")
        s = stories[item - 1]
        parts = [str(s.get("title", "")).strip()]
        if s.get("why"):
            parts.append(f"Why it matters: {s['why']}")
        if s.get("how_it_affects_me"):
            parts.append(f"How it affects you: {s['how_it_affects_me']}")
        return SkillReply(say=" ".join(p for p in parts if p))

    top = stories[:LIST_MAX]
    lines = []
    for s in top:
        why = str(s.get("why", "")).strip()
        title = str(s.get("title", "")).strip()
        lines.append(f"{title}: {why}" if why else title)
    numbered = " ".join(f"{i}. {line}" for i, line in enumerate(lines, 1))
    return SkillReply(say=f"{numbered} {ASK_MORE}", list_len=len(top))
