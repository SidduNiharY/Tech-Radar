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


def test_every_night_job_is_night_only() -> None:
    from techradar.night import night_jobs
    from techradar.worker.tasks import app

    names = night_jobs()
    # Phase 2c's two night jobs live on the queue; later tasks add theirs and this re-runs.
    assert {"ask_night", "summarize_chapters_job"} <= set(names)
    assert all(is_night_only(app.tasks[name]) for name in names)


def test_a_night_only_job_is_never_left_on_another_queue() -> None:
    from techradar.worker.names import NIGHT_QUEUE
    from techradar.worker.tasks import app

    stray = [
        name
        for name, task in app.tasks.items()
        if is_night_only(task) and task.queue != NIGHT_QUEUE
    ]
    assert stray == []


def test_the_worker_image_serves_the_night_queue() -> None:
    from pathlib import Path

    dockerfile = Path("infra/docker/Dockerfile").read_text()
    assert '"--queues=llm,io,night", "--concurrency=1"' in dockerfile
