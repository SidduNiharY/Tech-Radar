from __future__ import annotations

from datetime import date, datetime, time, timedelta

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
