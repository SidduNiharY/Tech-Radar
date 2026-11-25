"""Exams skill: exam dates with the latest alerts, or syllabus coverage."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import Alert, ExamWatch, SyllabusTopic
from techradar.exams.final30 import load_exam_dates
from techradar.exams.sources import topics_without_sources
from techradar.exams.syllabus import coverage
from techradar.jarvis.skill_impl.result import SkillReply

ALERTS_MAX = 3


async def _dates(session: AsyncSession, now: datetime, exam: str | None) -> SkillReply:
    dates = await load_exam_dates(session)
    if exam:
        dates = {k: v for k, v in dates.items() if k == exam}
    parts = []
    for name, when in sorted(dates.items(), key=lambda kv: kv[1]):
        days = (when - now.date()).days
        stamp = f"{when.day} {when.strftime('%b')}"
        if days > 0:
            parts.append(f"{name}: {stamp}, in {days} days.")
        elif days == 0:
            parts.append(f"{name}: today.")
        else:
            parts.append(f"{name}: {stamp}, already past.")
    alerts = (
        await session.execute(
            select(ExamWatch.title, Alert.changed_at)
            .join(ExamWatch, ExamWatch.id == Alert.watch_id)
            .order_by(Alert.changed_at.desc())
            .limit(ALERTS_MAX)
        )
    ).all()
    for title, changed in alerts:
        parts.append(f"Latest change: {title} on {changed.day} {changed.strftime('%b')}.")
    if not parts:
        return SkillReply(say="No exam dates are set and there are no exam alerts.")
    return SkillReply(say=" ".join(parts))


async def _progress(session: AsyncSession, exam: str | None) -> SkillReply:
    if exam:
        names = [exam]
    else:
        stmt = select(SyllabusTopic.exam).distinct().order_by(SyllabusTopic.exam)
        names = list((await session.execute(stmt)).scalars().all())
    if not names:
        return SkillReply(say="No syllabus is loaded yet.")
    parts = []
    for name in names:
        cov = await coverage(session, name)
        if not cov:
            parts.append(f"{name}: no syllabus topics yet.")
            continue
        covered = sum(1 for c in cov if c.covered)
        missing = len(await topics_without_sources(session, name))
        parts.append(f"{name}: {covered} of {len(cov)} topics covered, {missing} without a source.")
    return SkillReply(say=" ".join(parts))


async def run(
    session: AsyncSession, now: datetime, *, op: str = "dates", exam: str | None = None
) -> SkillReply:
    if op == "dates":
        return await _dates(session, now, exam)
    if op == "progress":
        return await _progress(session, exam)
    raise ValueError(f"unknown exams op: {op!r}")
