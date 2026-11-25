from __future__ import annotations

from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import Outbox
from techradar.db.models import UserSettings as UserSettingsRow
from techradar.messaging.outbox import enqueue_message

ENGLISH_REMINDER: str = (
    '🎙️ English practice time. Send a voice note, or open Jarvis and say "Coach my English".'
)


def reminder_due(
    now_local: datetime,
    at: time | None,
    last_sent: date | None,
) -> bool:
    """Determine whether an English practice reminder is currently due."""
    if at is None:
        return False

    now_date = now_local.date()
    if last_sent is not None and last_sent == now_date:
        return False

    # Window is [at, at + 2 hours]
    start_dt = datetime.combine(now_date, at)
    end_dt = start_dt + timedelta(hours=2)

    current_dt = datetime.combine(now_date, now_local.time())
    return start_dt <= current_dt <= end_dt


def parse_practice_time(value: object) -> time | None:
    """The stored `english_practice_time` (`HH:MM`); anything else means no reminder."""
    if not isinstance(value, str):
        return None
    try:
        return time.fromisoformat(value)
    except ValueError:
        return None


async def run_english_reminder(
    session: AsyncSession, now_local: datetime, *, owner_chat_id: int
) -> bool:
    """Send the practice reminder once per day, from the chosen time until two hours later.

    "Sent today" is read from the outbox itself, so a restart never repeats it. Coaching stays on
    demand (06 C2): this only reminds, it analyses nothing.
    """
    stored = (
        await session.execute(
            select(UserSettingsRow.value).where(UserSettingsRow.key == "english_practice_time")
        )
    ).scalar_one_or_none()
    at = parse_practice_time(stored)
    if at is None:
        return False
    last_created = (
        await session.execute(
            select(func.max(Outbox.created_at)).where(
                Outbox.chat_id == owner_chat_id, Outbox.purpose == "english_reminder"
            )
        )
    ).scalar_one_or_none()
    last_sent = last_created.astimezone(now_local.tzinfo).date() if last_created else None
    if not reminder_due(now_local, at, last_sent):
        return False
    await enqueue_message(session, owner_chat_id, ENGLISH_REMINDER, purpose="english_reminder")
    return True
