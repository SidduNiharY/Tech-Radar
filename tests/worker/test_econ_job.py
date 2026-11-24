from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from tests.worker.test_world_jobs import _wire


async def test_econ_collect_job_reads_stored_facts_only(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from techradar.worker import tasks

    seen = _wire(monkeypatch, tmp_path, hour=12)
    collect = AsyncMock(return_value=3)
    monkeypatch.setattr(tasks, "collect_official", collect)
    await tasks.econ_collect_job.func(timestamp=1)
    collect.assert_awaited_once()
    assert "rbi.org.in" in collect.call_args.args[1]
    seen["sessions"][0].commit.assert_awaited_once()
    assert tasks.econ_collect_job.queue == "io"
    crons = [
        p.cron
        for (n, _), p in tasks.app.periodic_registry.periodic_tasks.items()
        if n == "econ_collect_job"
    ]
    assert crons == ["0 3 * * *"]
