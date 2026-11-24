"""Glossary, timelines and chains jobs: queue, schedule, window and what they call."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from tests.worker.test_world_jobs import _wire


@pytest.mark.parametrize(
    "job,runner,cron",
    [
        ("glossary_job", "run_glossary", "0 20 * * *"),
        ("timelines_job", "run_timelines", "30 20 * * *"),
        ("chains_job", "run_chains", "0 21 * * *"),
    ],
)
async def test_night_page_jobs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, job: str, runner: str, cron: str
) -> None:
    from techradar.night import night_jobs
    from techradar.worker import tasks

    task = getattr(tasks, job)
    assert task.queue == "night" and job in night_jobs()
    assert [
        p.cron for (n, _), p in tasks.app.periodic_registry.periodic_tasks.items() if n == job
    ] == [cron]

    seen = _wire(monkeypatch, tmp_path, hour=12)
    run = AsyncMock(return_value=SimpleNamespace(model_dump=lambda: {}))
    monkeypatch.setattr(tasks, runner, run)
    await task.func(timestamp=1)
    run.assert_not_awaited()  # outside the window it only defers
    assert seen["deferred"][0][0] == job

    seen = _wire(monkeypatch, tmp_path, hour=2)
    await task.func(timestamp=1)
    run.assert_awaited_once()
    seen["sessions"][0].commit.assert_awaited_once()
    assert run.call_args.kwargs["vault_root"] == tmp_path / "vault"
