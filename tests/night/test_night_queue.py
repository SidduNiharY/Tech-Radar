from __future__ import annotations

from datetime import datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from techradar.night.window import is_night_only, night_only


async def test_night_only_reschedules_outside_window() -> None:
    calls: list[tuple[datetime, dict[str, Any]]] = []

    async def fake_defer(when: datetime, kwargs: dict[str, Any]) -> None:
        calls.append((when, kwargs))

    @night_only(
        task_name="test_job",
        defer=fake_defer,
        now=lambda: datetime(2026, 11, 8, 6, 0, tzinfo=ZoneInfo("Asia/Kolkata")),
        start=time(1, 0),
        end=time(5, 0),
        tz="Asia/Kolkata",
    )
    async def fake_job() -> int:
        return 42

    assert is_night_only(fake_job)
    res = await fake_job()
    assert res is None
    assert len(calls) == 1
    assert calls[0][0] == datetime(2026, 11, 9, 1, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
