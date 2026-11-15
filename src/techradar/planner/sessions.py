from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime, timedelta
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import LibraryChapter, LibraryDoc, Revision, StudySession


class Goal(StrEnum):
    DEV = "dev"
    GATE = "gate"
    GOV = "gov"
    CURRENT = "current"
    ENGLISH = "english"


_GOAL_KEYWORDS: dict[str, Goal] = {
    "gate": Goal.GATE,
    "gov": Goal.GOV,
    "ssc": Goal.GOV,
    "bank": Goal.GOV,
    "dev": Goal.DEV,
    "current": Goal.CURRENT,
    "news": Goal.CURRENT,
    "english": Goal.ENGLISH,
}


def parse_study_command(arg: str) -> tuple[Goal, str] | None:
    """Parses /study arguments into (Goal, topic)."""
    parts = arg.strip().split(maxsplit=1)
    if not parts:
        return None
    keyword = parts[0].lower()
    if keyword not in _GOAL_KEYWORDS:
        return None
    if len(parts) < 2:
        return None
    topic = parts[1].strip()
    if not (1 <= len(topic) <= 120):
        return None
    return _GOAL_KEYWORDS[keyword], topic


def revision_dates(day: date, goal: Goal) -> list[date]:
    """Calculate 1-7-30 (+90 for exam goals) revision dates."""
    dates = [
        day + timedelta(days=1),
        day + timedelta(days=7),
        day + timedelta(days=30),
    ]
    if goal in (Goal.GATE, Goal.GOV):
        dates.append(day + timedelta(days=90))
    return dates


def join_dates(ds: Sequence[date]) -> str:
    """Format dates into '9 Nov, 15 Nov and 8 Dec'."""
    formatted = [f"{d.day} {d.strftime('%b')}" for d in ds]
    if not formatted:
        return ""
    if len(formatted) == 1:
        return formatted[0]
    if len(formatted) == 2:
        return f"{formatted[0]} and {formatted[1]}"
    return f"{', '.join(formatted[:-1])} and {formatted[-1]}"


def goal_for_doc(exam_tags: Sequence[str]) -> Goal:
    """Determine goal for a document based on its exam tags."""
    tags = [t.lower() for t in exam_tags]
    if any("gate" in t for t in tags):
        return Goal.GATE
    if any(k in t for t in tags for k in ("ssc_cgl", "ssc", "bank", "gov")):
        return Goal.GOV
    return Goal.CURRENT


class StudyStop(BaseModel):
    model_config = ConfigDict(extra="forbid")

    minutes: int
    goal: Goal
    topic: str
    revision_dates: list[date]


async def start_session(
    session: AsyncSession,
    goal: Goal,
    topic: str,
    now: datetime,
) -> Literal["started", "already_running"]:
    """Starts a study session if no session is currently active."""
    stmt = select(StudySession).where(StudySession.ended_at.is_(None)).limit(1)
    res = await session.execute(stmt)
    if res.scalar_one_or_none() is not None:
        return "already_running"

    new_session = StudySession(
        goal=goal.value,
        topic=topic,
        started_at=now,
    )
    session.add(new_session)
    await session.flush()
    return "started"


async def stop_session(session: AsyncSession, now: datetime) -> StudyStop | None:
    """Stops the currently running study session and schedules revisions."""
    stmt = (
        select(StudySession)
        .where(StudySession.ended_at.is_(None))
        .order_by(StudySession.started_at.desc())
        .limit(1)
    )
    res = await session.execute(stmt)
    s = res.scalar_one_or_none()
    if s is None:
        return None

    raw_min = int((now - s.started_at).total_seconds() / 60)
    minutes = max(1, min(240, raw_min))
    s.ended_at = now
    s.minutes = minutes

    # Check for existing pending revisions for topic
    rev_check = select(Revision).where(
        Revision.topic == s.topic,
        Revision.done_at.is_(None),
    )
    existing_pending = (await session.execute(rev_check)).scalars().first()
    g = Goal(s.goal)
    if existing_pending is None:
        rev_dates = revision_dates(now.date(), g)
        for rd in rev_dates:
            session.add(
                Revision(
                    goal=s.goal,
                    topic=s.topic,
                    due_date=rd,
                    session_id=s.id,
                )
            )
    else:
        rev_dates = []

    await session.flush()
    return StudyStop(
        minutes=minutes,
        goal=g,
        topic=s.topic,
        revision_dates=rev_dates,
    )


async def schedule_chapter_revisions(
    session: AsyncSession,
    chapter_id: int,
    read_on: date,
) -> list[date]:
    """Schedule revisions for a read book chapter."""
    stmt = select(Revision).where(Revision.chapter_id == chapter_id)
    if (await session.execute(stmt)).scalars().first() is not None:
        return []

    ch_stmt = select(LibraryChapter).where(LibraryChapter.id == chapter_id)
    chapter = (await session.execute(ch_stmt)).scalar_one()

    doc_stmt = select(LibraryDoc).where(LibraryDoc.id == chapter.doc_id)
    doc = (await session.execute(doc_stmt)).scalar_one()

    topic = f"{doc.title} · {chapter.title}"
    goal = goal_for_doc(doc.exam_tags or [])
    rev_dates = revision_dates(read_on, goal)

    for rd in rev_dates:
        session.add(
            Revision(
                goal=goal.value,
                topic=topic,
                due_date=rd,
                chapter_id=chapter_id,
            )
        )

    await session.flush()
    return rev_dates


async def close_stale_sessions(session: AsyncSession, now: datetime) -> int:
    """Closes sessions running longer than 4 hours."""
    stale_threshold = now - timedelta(hours=4)
    stmt = select(StudySession).where(
        StudySession.ended_at.is_(None),
        StudySession.started_at <= stale_threshold,
    )
    stale_sessions = (await session.execute(stmt)).scalars().all()
    count = 0
    for s in stale_sessions:
        s.ended_at = s.started_at + timedelta(hours=4)
        s.minutes = 240
        s.auto_closed = True

        rev_check = select(Revision).where(
            Revision.topic == s.topic,
            Revision.done_at.is_(None),
        )
        if (await session.execute(rev_check)).scalars().first() is None:
            g = Goal(s.goal)
            rev_dates = revision_dates(s.ended_at.date(), g)
            for rd in rev_dates:
                session.add(
                    Revision(
                        goal=s.goal,
                        topic=s.topic,
                        due_date=rd,
                        session_id=s.id,
                    )
                )
        count += 1

    await session.flush()
    return count


async def run_close_stale_sessions(session: AsyncSession, now: datetime) -> int:
    """Alias runner for close_stale_sessions."""
    return await close_stale_sessions(session, now)
