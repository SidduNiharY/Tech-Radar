"""The prediction jobs: a daily reminder at 08:00 IST and the vault page refresh."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from tests.worker.test_world_jobs import _wire


def test_reminder_is_daily_at_0800_ist_on_the_io_queue() -> None:
    from techradar.worker.tasks import app, prediction_reminder_job, predictions_sync_job

    assert (prediction_reminder_job.name, prediction_reminder_job.queue) == (
        "prediction_reminder_job",
        "io",
    )
    crons = [
        p.cron
        for (n, _), p in app.periodic_registry.periodic_tasks.items()
        if n == "prediction_reminder_job"
    ]
    assert crons == ["30 2 * * *"]  # 02:30 UTC is 08:00 in Asia/Kolkata
    assert predictions_sync_job.name == "predictions_sync_job"


async def test_reminder_job_uses_the_owner_from_settings_and_queues_the_refresh(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from techradar.worker import tasks

    seen = _wire(monkeypatch, tmp_path, hour=2)
    run = AsyncMock(return_value=2)
    monkeypatch.setattr(tasks, "run_prediction_reminder", run)
    defer = AsyncMock()
    monkeypatch.setattr(tasks, "predictions_sync_job", SimpleNamespace(defer_async=defer))
    await tasks.prediction_reminder_job.func(timestamp=1)
    kwargs = run.call_args.kwargs
    assert kwargs["owner_chat_id"] == 4242 and kwargs["tz"] == "UTC"
    seen["sessions"][0].commit.assert_awaited_once()
    defer.assert_awaited_once()
