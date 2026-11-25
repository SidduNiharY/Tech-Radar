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


def test_parse_practice_time() -> None:
    from techradar.voice.practice_time import parse_practice_time

    assert parse_practice_time("19:30") == time(19, 30)
    assert parse_practice_time(None) is None
    assert parse_practice_time("soon") is None
    assert parse_practice_time(1930) is None


class _Result:
    def __init__(self, value: object) -> None:
        self._value = value

    def scalar_one_or_none(self) -> object:
        return self._value


class _FakeSession:
    """Answers the two reads of run_english_reminder: the stored time, then the last send."""

    def __init__(self, stored: object, last_created: datetime | None) -> None:
        self._answers = [stored, last_created]

    async def execute(self, _stmt: object) -> _Result:
        return _Result(self._answers.pop(0))


async def test_run_english_reminder_sends_once(monkeypatch: pytest.MonkeyPatch) -> None:
    from datetime import UTC
    from zoneinfo import ZoneInfo

    from techradar.voice import practice_time

    sent: list[tuple[int, str, str]] = []

    async def fake_enqueue(session: object, chat_id: int, text: str, *, purpose: str) -> int:
        sent.append((chat_id, text, purpose))
        return 1

    monkeypatch.setattr(practice_time, "enqueue_message", fake_enqueue)
    ist = ZoneInfo("Asia/Kolkata")
    now = datetime(2026, 11, 15, 19, 10, tzinfo=ist)

    assert (
        await practice_time.run_english_reminder(_FakeSession(None, None), now, owner_chat_id=5)
        is False
    )
    assert await practice_time.run_english_reminder(
        _FakeSession("19:00", None), now, owner_chat_id=5
    )
    assert sent == [(5, ENGLISH_REMINDER, "english_reminder")]
    already = datetime(2026, 11, 15, 13, 40, tzinfo=UTC)  # 19:10 IST the same day
    assert not await practice_time.run_english_reminder(
        _FakeSession("19:00", already), now, owner_chat_id=5
    )
    assert len(sent) == 1
