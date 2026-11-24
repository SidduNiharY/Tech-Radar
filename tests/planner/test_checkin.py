from __future__ import annotations

from datetime import date

import pytest

from techradar.planner.checkin import (
    CHECKIN_TEXT,
    checkin_keyboard,
    get_checkin,
    record_checkin,
)

TODAY = date(2026, 11, 15)


def test_checkin_keyboard_data():
    kb = checkin_keyboard()
    assert [b.data for b in kb[0]] == [f"sleep:{i}" for i in range(1, 6)]
    assert [b.data for b in kb[1]] == [f"energy:{i}" for i in range(1, 6)]
    assert [b.data for b in kb[2]] == [f"mood:{i}" for i in range(1, 6)]
    assert len(kb) == 3
    assert CHECKIN_TEXT.startswith("How did you sleep")


@pytest.mark.db
@pytest.mark.asyncio
async def test_record_checkin_upserts(session):
    await record_checkin(session, TODAY, "sleep", 2)
    await record_checkin(session, TODAY, "sleep", 4)
    assert await get_checkin(session, TODAY) == {
        "sleep_band": 4,
        "energy": None,
        "mood": None,
    }


@pytest.mark.db
@pytest.mark.asyncio
async def test_record_checkin_rejects_out_of_range(session):
    with pytest.raises(ValueError, match="between 1 and 5"):
        await record_checkin(session, TODAY, "mood", 9)
    with pytest.raises(ValueError, match="between 1 and 5"):
        await record_checkin(session, TODAY, "energy", 0)


@pytest.mark.db
@pytest.mark.asyncio
async def test_after_briefing_sends_checkin_once_per_day(session):
    from datetime import UTC, datetime

    from sqlalchemy import select

    from techradar.db.models import Outbox
    from techradar.planner.checkin import after_briefing

    now = datetime(2026, 11, 15, 1, 30, tzinfo=UTC)
    assert await after_briefing(session, 4242, now) is True
    assert await after_briefing(session, 4242, now) is False  # a retry or catch-up run
    rows = (await session.execute(select(Outbox).where(Outbox.purpose == "checkin"))).scalars()
    msgs = [m for m in rows if m.chat_id == 4242]
    assert len(msgs) == 1 and msgs[0].text.startswith("How did you sleep")
    assert msgs[0].buttons[0][0]["data"] == "sleep:1"
