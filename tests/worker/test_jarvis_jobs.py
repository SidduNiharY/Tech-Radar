from __future__ import annotations

import inspect
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from tests.worker.test_world_jobs import _wire


def test_greeting_job_is_periodic_and_takes_timestamp() -> None:
    from techradar.worker.tasks import app, greeting_job

    assert (greeting_job.name, greeting_job.queue) == ("greeting_job", "io")
    assert "timestamp" in inspect.signature(greeting_job.func).parameters
    crons = [
        p.cron for (n, _), p in app.periodic_registry.periodic_tasks.items() if n == "greeting_job"
    ]
    assert crons == ["*/15 * * * *"]


async def test_greeting_job_prepares_with_local_time_and_commits(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from techradar.worker import tasks

    seen = _wire(monkeypatch, tmp_path, hour=7)
    prepare = AsyncMock(return_value=None)
    monkeypatch.setattr(tasks, "run_prepare_greeting", prepare)
    await tasks.greeting_job.func(timestamp=1)
    prepare.assert_awaited_once()
    now = prepare.call_args.args[1]
    assert isinstance(now, datetime) and now.tzinfo is not None
    assert now.utcoffset() == UTC.utcoffset(now)  # the wired settings use tz=UTC
    seen["sessions"][0].commit.assert_awaited_once()
