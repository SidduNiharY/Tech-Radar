from __future__ import annotations

from datetime import UTC, datetime, time
from zoneinfo import ZoneInfo

import pytest

from techradar.night.window import in_night_window, next_window_start, night_only

IST = ZoneInfo("Asia/Kolkata")
START, END = time(1, 0), time(5, 0)


@pytest.mark.parametrize(
    "hhmm,inside", [("00:59", False), ("01:00", True), ("04:59", True), ("05:00", False)]
)
def test_in_night_window(hhmm, inside):
    h, m = map(int, hhmm.split(":"))
    assert in_night_window(datetime(2026, 11, 8, h, m, tzinfo=IST), START, END) is inside


def test_window_crossing_midnight():
    s, e = time(23, 0), time(2, 0)
    assert in_night_window(datetime(2026, 1, 1, 23, 0), s, e)
    assert in_night_window(datetime(2026, 1, 1, 1, 59), s, e)
    assert not in_night_window(datetime(2026, 1, 1, 2, 0), s, e)
    assert not in_night_window(datetime(2026, 1, 1, 12, 0), s, e)


def test_next_window_start():
    assert next_window_start(datetime(2026, 11, 8, 6, 0, tzinfo=IST), START) == datetime(
        2026, 11, 9, 1, 0, tzinfo=IST
    )
    assert next_window_start(datetime(2026, 11, 8, 0, 30, tzinfo=IST), START) == datetime(
        2026, 11, 8, 1, 0, tzinfo=IST
    )
    # exactly at start: that start has begun, so the next one is tomorrow
    assert next_window_start(datetime(2026, 11, 8, 1, 0, tzinfo=IST), START) == datetime(
        2026, 11, 9, 1, 0, tzinfo=IST
    )


class Recorder:
    def __init__(self):
        self.events: list = []

    async def defer(self, when, kwargs):
        self.events.append(("defer", when, kwargs))

    async def free(self):
        self.events.append(("free",))


def _make(rec, utc_now):
    calls: list = []

    @night_only(
        defer=rec.defer,
        free=rec.free,
        now=lambda: utc_now,
        start=START,
        end=END,
        tz="Asia/Kolkata",
    )
    async def job(doc_id: int):
        rec.events.append(("run", doc_id))
        calls.append(doc_id)
        return "done"

    return job, calls


async def test_night_only_reschedules_outside_window():
    rec = Recorder()
    # 06:00 IST = 00:30 UTC
    job, calls = _make(rec, datetime(2026, 11, 8, 0, 30, tzinfo=UTC))
    assert await job(doc_id=5) is None
    assert calls == []
    assert rec.events == [("defer", datetime(2026, 11, 9, 1, 0, tzinfo=IST), {"doc_id": 5})]


async def test_night_only_frees_gpu_then_runs_inside_window():
    rec = Recorder()
    # 02:00 IST = 20:30 UTC previous day
    job, _ = _make(rec, datetime(2026, 11, 7, 20, 30, tzinfo=UTC))
    assert await job(doc_id=9) == "done"
    assert rec.events == [("free",), ("run", 9)]
