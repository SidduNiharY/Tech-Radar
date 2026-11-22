from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import Checkin, Outbox
from techradar.messaging.outbox import Button, enqueue_message
from techradar.planner.sessions import local_date

CHECKIN_TEXT = "How did you sleep, and how's your energy and mood today? (one tap each)"

_SLEEP_LABELS = ["<5h", "5–6", "6–7", "7–8", "8+"]


def checkin_keyboard() -> list[list[Button]]:
    """Builds inline button keyboard for sleep, energy and mood check-in."""
    sleep_row = [Button(text=_SLEEP_LABELS[i - 1], data=f"sleep:{i}") for i in range(1, 6)]
    energy_row = [Button(text=str(i), data=f"energy:{i}") for i in range(1, 6)]
    mood_row = [Button(text=str(i), data=f"mood:{i}") for i in range(1, 6)]
    return [sleep_row, energy_row, mood_row]


async def record_checkin(
    session: AsyncSession,
    day: date,
    field: Literal["sleep", "energy", "mood"],
    value: int,
) -> None:
    """Upserts a daily checkin score for sleep, energy, or mood."""
    if not (1 <= value <= 5):
        raise ValueError(f"{field} value must be between 1 and 5, got {value}")

    stmt = select(Checkin).where(Checkin.date == day)
    res = await session.execute(stmt)
    c = res.scalar_one_or_none()

    if c is None:
        c = Checkin(date=day)
        session.add(c)

    if field == "sleep":
        c.sleep_band = value
    elif field == "energy":
        c.energy = value
    elif field == "mood":
        c.mood = value

    await session.flush()


async def get_checkin(session: AsyncSession, day: date) -> dict[str, Any] | None:
    """Retrieves checkin scores for a given date."""
    stmt = select(Checkin).where(Checkin.date == day)
    res = await session.execute(stmt)
    c = res.scalar_one_or_none()
    if c is None:
        return None
    return {
        "sleep_band": c.sleep_band,
        "energy": c.energy,
        "mood": c.mood,
    }


CHECKIN_PURPOSE = "checkin"


async def after_briefing(session: AsyncSession, owner_chat_id: int, now: datetime) -> bool:
    """Send the one-tap check-in right after the briefing; once per India day.

    WIRING(claude): the briefing job (Phase 3) calls this after `run_briefing` sent a briefing.
    It is safe to call again (a catch-up run, a retry): the day is the dedupe key.
    """
    ref = int(local_date(now).strftime("%Y%m%d"))
    already = await session.execute(
        select(Outbox.id)
        .where(
            Outbox.purpose == CHECKIN_PURPOSE,
            Outbox.ref_id == ref,
            Outbox.chat_id == owner_chat_id,
        )
        .limit(1)
    )
    if already.scalar_one_or_none() is not None:
        return False
    await enqueue_message(
        session,
        chat_id=owner_chat_id,
        text=CHECKIN_TEXT,
        purpose=CHECKIN_PURPOSE,
        buttons=checkin_keyboard(),
        ref_id=ref,
    )
    return True
