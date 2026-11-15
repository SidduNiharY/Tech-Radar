from __future__ import annotations

from datetime import date, datetime, time

import pytest

from techradar.voice.practice_time import ENGLISH_REMINDER, reminder_due

TODAY = date(2026, 11, 15)


def at_local(hhmm: str) -> datetime:
    parts = hhmm.split(":")
    h, m = int(parts[0]), int(parts[1])
    return datetime.combine(TODAY, time(h, m))


@pytest.mark.parametrize(
    "hhmm,last,due",
    [
        ("18:59", None, False),
        ("19:00", None, True),
        ("21:01", None, False),
        ("19:30", "today", False),
    ],
)
def test_reminder_due(hhmm: str, last: str | None, due: bool) -> None:
    assert reminder_due(at_local(hhmm), time(19, 0), TODAY if last else None) is due


def test_no_time_means_no_reminder() -> None:
    assert reminder_due(at_local("19:00"), None, None) is False
    assert "English practice time" in ENGLISH_REMINDER
