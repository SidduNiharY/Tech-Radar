from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select

from techradar.db.models import LibraryChapter, LibraryDoc, StudySession
from techradar.planner.sessions import (
    Goal,
    close_stale_sessions,
    goal_for_doc,
    join_dates,
    parse_study_command,
    revision_dates,
    schedule_chapter_revisions,
    start_session,
    stop_session,
)

NOW = datetime(2026, 11, 8, 10, 0, tzinfo=UTC)


def test_parse_study_command():
    assert parse_study_command("gate operating systems") == (Goal.GATE, "operating systems")
    assert parse_study_command("bank percentages") == (Goal.GOV, "percentages")
    assert parse_study_command("cooking") is None
    assert parse_study_command("") is None
    assert parse_study_command("dev") is None
    assert parse_study_command("english idioms") == (Goal.ENGLISH, "idioms")


def test_revision_dates():
    assert revision_dates(date(2026, 11, 8), Goal.DEV) == [
        date(2026, 11, 9),
        date(2026, 11, 15),
        date(2026, 12, 8),
    ]
    assert revision_dates(date(2026, 11, 8), Goal.GATE)[-1] == date(2027, 2, 6)
    assert len(revision_dates(date(2026, 11, 8), Goal.GOV)) == 4


def test_join_dates():
    assert (
        join_dates([date(2026, 11, 9), date(2026, 11, 15), date(2026, 12, 8)])
        == "9 Nov, 15 Nov and 8 Dec"
    )
    assert join_dates([date(2026, 11, 9)]) == "9 Nov"
    assert join_dates([date(2026, 11, 9), date(2026, 11, 15)]) == "9 Nov and 15 Nov"
    assert join_dates([]) == ""


def test_goal_for_doc():
    assert goal_for_doc(["GATE", "CS"]) == Goal.GATE
    assert goal_for_doc(["ssc_cgl"]) == Goal.GOV
    assert goal_for_doc(["Bank_PO"]) == Goal.GOV
    assert goal_for_doc(["tech"]) == Goal.CURRENT


@pytest.mark.db
@pytest.mark.asyncio
async def test_chapter_revisions_include_90_for_exam_books(session):
    doc = LibraryDoc(
        source_id=0,
        slug="gate-cs-primer",
        title="GATE CS Operating Systems",
        doc_path="gate/os.pdf",
        kind="book",
        exam_tags=["GATE"],
    )
    session.add(doc)
    await session.flush()

    chapter = LibraryChapter(
        doc_id=doc.id,
        ordinal=1,
        title="Virtual Memory",
        text_path="gate/ch01.txt",
    )
    session.add(chapter)
    await session.flush()

    ds = await schedule_chapter_revisions(session, chapter.id, date(2026, 11, 8))
    assert len(ds) == 4
    # Idempotent: second call returns empty
    assert await schedule_chapter_revisions(session, chapter.id, date(2026, 11, 8)) == []


@pytest.mark.db
@pytest.mark.asyncio
async def test_start_when_running(session):
    assert await start_session(session, Goal.GATE, "os", NOW) == "started"
    assert await start_session(session, Goal.DEV, "x", NOW) == "already_running"


@pytest.mark.db
@pytest.mark.asyncio
async def test_stop_creates_revisions(session):
    await start_session(session, Goal.GATE, "os", NOW)
    s = await stop_session(session, NOW + timedelta(minutes=45))
    assert s is not None
    assert s.minutes == 45
    assert len(s.revision_dates) == 4  # GATE gets +90


@pytest.mark.db
@pytest.mark.asyncio
async def test_stale_session_auto_closed(session):
    await start_session(session, Goal.GATE, "os", NOW)
    closed = await close_stale_sessions(session, NOW + timedelta(hours=5))
    assert closed == 1

    stmt = select(StudySession).where(StudySession.topic == "os")
    s = (await session.execute(stmt)).scalar_one()
    assert s.auto_closed is True
    assert s.minutes == 240
