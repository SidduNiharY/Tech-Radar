"""Phase 5 jobs are declared the way the worker needs, and call the plain logic."""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace

from techradar.worker import tasks
from techradar.worker.app import app


def test_close_stale_sessions_job_declaration():
    job = tasks.close_stale_sessions_job
    assert job.name == "close_stale_sessions_job"
    assert job.queue == "io"
    assert app.tasks["close_stale_sessions_job"] is job
    assert job.queueing_lock  # a tick is skipped while one waits: no pile-up after downtime


def test_health_job_declaration():
    job = tasks.health_job
    assert job.name == "health_job"
    assert job.queueing_lock
    periodic = [p for p in app.periodic_registry.periodic_tasks.values() if p.task is job]
    assert [p.cron for p in periodic] == ["5 * * * *"]


def test_existing_jobs_are_wrapped_with_failure_alerts():
    # functools.wraps keeps the name; the wrapper is the one alert_on_failure made
    for job in (
        tasks.collect_and_process,
        tasks.retention,
        tasks.index_sync,
        tasks.collect_bulk_results_job,
        tasks.resume_bulk_job,
        tasks.close_stale_sessions_job,
        tasks.weekly_review_job,
        tasks.health_job,
    ):
        assert hasattr(job.func, "__wrapped__"), job.name


def test_weekly_review_job_declaration():
    job = tasks.weekly_review_job
    assert job.name == "weekly_review_job"
    assert job.queue == "io"
    assert job.queueing_lock
    # Sundays 19:00 India time is 13:30 UTC (procrastinate reads cron in UTC)
    periodic = [p for p in app.periodic_registry.periodic_tasks.values() if p.task is job]
    assert [p.cron for p in periodic] == ["30 13 * * 0"]


async def test_close_stale_sessions_job_commits(monkeypatch):
    calls: list[str] = []

    class FakeSession:
        async def commit(self) -> None:
            calls.append("commit")

    @asynccontextmanager
    async def factory():
        yield FakeSession()

    async def fake_close(session, now):
        calls.append("close")
        return 2

    monkeypatch.setattr(tasks, "make_session_factory", lambda *a, **k: factory)
    monkeypatch.setattr(tasks, "close_stale_sessions", fake_close)
    monkeypatch.setattr(tasks, "_get_settings", lambda: SimpleNamespace())
    await tasks.close_stale_sessions_job()
    assert calls == ["close", "commit"]
