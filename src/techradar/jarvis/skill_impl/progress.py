"""Progress skill: this week's minutes per goal against the targets, and the weakest topic."""

from __future__ import annotations

from datetime import datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import StudySession, TopicMastery, UserSettings
from techradar.jarvis.skill_impl.result import SkillReply

DEFAULT_TARGETS = {"dev": 600, "gate": 300, "gov": 420, "current": 105, "english": 140}
LEVELS = ["new", "learning", "exam_ready", "mastered"]


async def _targets(session: AsyncSession) -> dict[str, int]:
    row = await session.get(UserSettings, "weekly_targets_min")
    if row and isinstance(row.value, dict):
        out = {str(k): int(v) for k, v in row.value.items() if isinstance(v, int)}
        if out:
            return out
    return dict(DEFAULT_TARGETS)


async def _weakest_topic(session: AsyncSession) -> str | None:
    rows = (
        await session.execute(select(TopicMastery).where(TopicMastery.prev_level.is_not(None)))
    ).scalars()
    worst: tuple[int, str] | None = None
    for r in rows:
        if r.level not in LEVELS or r.prev_level not in LEVELS:
            continue
        drop = LEVELS.index(r.prev_level) - LEVELS.index(r.level)
        if drop > 0 and (worst is None or drop > worst[0]):
            worst = (drop, r.topic)
    return worst[1] if worst else None


async def run(session: AsyncSession, now: datetime, *, goal: str | None = None) -> SkillReply:
    day = now.date()
    monday = day - timedelta(days=day.weekday())
    week_start = datetime.combine(monday, time.min, now.tzinfo)
    rows = (
        await session.execute(
            select(StudySession.goal, func.coalesce(func.sum(StudySession.minutes), 0))
            .where(StudySession.started_at >= week_start, StudySession.minutes.is_not(None))
            .group_by(StudySession.goal)
        )
    ).all()
    sums = {g: int(m) for g, m in rows}
    targets = await _targets(session)
    goals = [goal] if goal else sorted(targets)
    parts = [f"{g}: {sums.get(g, 0)} of {targets.get(g, 0)} minutes." for g in goals]
    say = "This week, " + " ".join(parts)
    weak = await _weakest_topic(session)
    if weak and goal is None:
        say += f" The topic that slipped most is {weak}."
    return SkillReply(say=say)
