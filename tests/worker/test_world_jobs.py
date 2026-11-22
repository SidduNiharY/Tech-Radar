"""The Phase 7 jobs in worker/tasks.py: queue, window, schedule and what they call."""

from __future__ import annotations

import inspect
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

OWNER = 4242


def _wire(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *, hour: int) -> dict[str, Any]:
    """Fix the clock (UTC, so the night window is 01:00 to 05:00 by the clock above)."""
    from techradar.night import window
    from techradar.worker import tasks

    seen: dict[str, Any] = {"deferred": [], "sessions": []}
    settings = SimpleNamespace(
        night_start="01:00",
        night_end="05:00",
        tz="UTC",
        telegram_owner_chat_id=OWNER,
        data_dir=tmp_path,
    )
    monkeypatch.setattr(tasks, "_get_settings", lambda: settings)
    monkeypatch.setattr("techradar.settings.get_settings", lambda: settings)
    monkeypatch.setattr(window, "_utc_now", lambda: datetime(2026, 11, 14, hour, 0, tzinfo=UTC))

    async def free() -> list[str]:
        return []

    monkeypatch.setattr(window, "_default_free", free)

    def default_defer(task_name: str) -> Any:
        async def defer(when: Any, kwargs: dict[str, Any]) -> None:
            seen["deferred"].append((task_name, when, kwargs))

        return defer

    monkeypatch.setattr(window, "_default_defer", default_defer)
    monkeypatch.setattr(tasks, "get_rag_deps", lambda: "deps")

    @asynccontextmanager
    async def factory() -> Any:
        session = MagicMock()
        session.commit = AsyncMock()
        seen["sessions"].append(session)
        yield session

    monkeypatch.setattr(tasks, "make_session_factory", lambda *_a, **_k: factory)
    return seen


def test_deep_dive_job_is_a_weekly_night_only_job_on_the_night_queue() -> None:
    from techradar.worker.tasks import app, deep_dive_job

    assert (deep_dive_job.name, deep_dive_job.queue) == ("deep_dive_job", "night")
    assert hasattr(deep_dive_job.func, "__wrapped__")  # wrapped by night_only
    periodic = [
        p
        for (name, _), p in app.periodic_registry.periodic_tasks.items()
        if name == "deep_dive_job"
    ]
    assert [p.cron for p in periodic] == ["30 21 * * 6"]
    # procrastinate passes `timestamp` to every periodic job
    wrapped = deep_dive_job.func.__wrapped__  # type: ignore[attr-defined]
    assert "timestamp" in inspect.signature(wrapped).parameters


async def test_deep_dive_job_outside_the_window_is_deferred(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from techradar.worker import tasks

    seen = _wire(monkeypatch, tmp_path, hour=12)
    run = AsyncMock()
    monkeypatch.setattr(tasks, "run_deep_dive", run)
    await tasks.deep_dive_job.func(timestamp=1)
    run.assert_not_awaited()
    ((name, _when, kwargs),) = seen["deferred"]
    assert (name, kwargs) == ("deep_dive_job", {"timestamp": 1})


async def test_deep_dive_job_in_the_window_runs_commits_and_uses_the_owner_from_settings(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from techradar.worker import tasks

    seen = _wire(monkeypatch, tmp_path, hour=2)
    run = AsyncMock(return_value=SimpleNamespace(model_dump=lambda: {"status": "written"}))
    monkeypatch.setattr(tasks, "run_deep_dive", run)
    await tasks.deep_dive_job.func(timestamp=1)
    assert seen["deferred"] == []
    (session,) = seen["sessions"]
    session.commit.assert_awaited_once()
    args, kwargs = run.call_args
    assert args == (session,)
    assert kwargs["deps"] == "deps" and kwargs["owner_chat_id"] == OWNER
    assert kwargs["vault_root"] == tmp_path / "vault"
    assert kwargs["now"].tzinfo is not None
