"""The server is off for 30 hours: everything catches up once (Phase 5 Task 7, D19).

The clock is frozen: every job body takes `now`. The worker stops at T and starts at T+30h,
then each periodic job body runs once, and then runs again (a second tick must change
nothing). The pieces that need no database are checked first; the rest is `db`-marked.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from techradar.briefing.compose import briefing_due, run_briefing
from techradar.db.models import Briefing, Outbox, Revision, StudySession
from techradar.fetcher.due import SourceRow, due_sources
from techradar.ops.health import run_health_checks
from techradar.planner.checkin import after_briefing
from techradar.planner.plan import plan_for_today
from techradar.planner.sessions import close_stale_sessions

IST = ZoneInfo("Asia/Kolkata")
OWNER = 4242
# The worker stops at 12:00 on Sunday 8 Nov (India) and starts at 18:00 on Monday 9 Nov.
T = datetime(2026, 11, 8, 12, 0, tzinfo=IST)
RESTART = T + timedelta(hours=30)


def test_the_briefing_is_not_sent_late_after_the_grace_period():
    # Monday's 06:30 briefing was missed; at 18:00 the 6-hour grace period is over
    assert not briefing_due(RESTART, date(2026, 11, 8), time(6, 30), 21600)
    # one hour after the start time it would still have been sent
    assert briefing_due(RESTART.replace(hour=7, minute=30), date(2026, 11, 8), time(6, 30), 21600)


def test_each_overdue_source_is_fetched_once_not_once_per_missed_interval():
    rows = [
        SourceRow(1, "https://a.example/feed", 120, T, True),
        SourceRow(2, "https://b.example/feed", 120, T, True),
        SourceRow(3, "https://c.example/feed", 120, T, False),  # disabled: never fetched
    ]
    assert [s.id for s in due_sources(rows, RESTART)] == [1, 2]
    fetched = [s._replace(last_fetched_at=RESTART) for s in rows]
    assert due_sources(fetched, RESTART + timedelta(minutes=1)) == []


@pytest.mark.db
@pytest.mark.asyncio
async def test_catch_up_after_30_hours(session):
    t_utc = T.astimezone(UTC)
    restart = RESTART.astimezone(UTC)

    # state at T: a session left running, a revision due Monday (inside the gap), and
    # Sunday's briefing already sent
    session.add(StudySession(goal="gate", topic="os", started_at=t_utc - timedelta(hours=1)))
    session.add(Revision(goal="gate", topic="dbms", due_date=date(2026, 11, 9)))
    session.add(Briefing(date=date(2026, 11, 8), sent_at=t_utc - timedelta(hours=5)))
    await session.flush()

    first_alerts: list[str] = []
    for tick in range(2):  # the first tick catches up, the second must change nothing
        closed = await close_stale_sessions(session, restart)
        assert (closed >= 1) if tick == 0 else (closed == 0)

        briefing = await run_briefing(session, now=RESTART, owner_chat_id=OWNER)
        assert briefing.skipped_reason == "not_due"  # no late briefing

        sent = await run_health_checks(
            session,
            now=restart,
            owner_chat_id=OWNER,
            disk_free_pct=5.0,
            ollama_ok=False,
            backup_status=None,
        )
        if tick == 0:
            first_alerts = sent
            assert {"disk", "ollama", "backup"} <= set(sent)
        else:
            assert sent == []  # one alert per key

        await plan_for_today(session, restart)

    rows = (await session.execute(select(Outbox).where(Outbox.chat_id == OWNER))).scalars().all()
    assert sorted(m.purpose for m in rows) == ["alert"] * len(
        first_alerts
    )  # no briefing, no check-in
    assert (
        await session.execute(select(Briefing).where(Briefing.date == RESTART.date()))
    ).first() is None

    # the stale session was closed at 4 hours, and its +1 day revision plus the one that fell
    # due in the gap are both in the plan (the plan row is stored once per day)
    stale = (
        await session.execute(select(StudySession).where(StudySession.topic == "os"))
    ).scalar_one()
    assert stale.auto_closed and stale.minutes == 240
    pending = (
        await session.execute(select(Revision.topic).where(Revision.due_date <= RESTART.date()))
    ).scalars()
    assert {"dbms", "os"} <= set(pending)
    lines = await plan_for_today(session, restart)
    assert any("topic revisions" in line for line in lines)

    # when the briefing does run on Tuesday morning, the check-in follows it exactly once
    morning = datetime(2026, 11, 10, 6, 45, tzinfo=IST)
    assert await after_briefing(session, OWNER, morning) is True
    assert await after_briefing(session, OWNER, morning) is False
