"""Every periodic job must accept `timestamp=`.

procrastinate defers each periodic task with `task_kwargs["timestamp"] = <defer time>`
(procrastinate/periodic.py), so a periodic job without that parameter raises TypeError
on every run. The Phase 2c and Phase 5 jobs had this bug until 2026-11-24.
"""

import inspect

import techradar.worker.tasks  # noqa: F401  (registers the tasks)
from techradar.worker.app import app


def _accepts_timestamp(func) -> bool:
    params = inspect.signature(func).parameters
    return "timestamp" in params or any(p.kind is p.VAR_KEYWORD for p in params.values())


def test_there_are_periodic_jobs():
    assert len(app.periodic_registry.periodic_tasks) >= 10


def test_every_periodic_job_accepts_the_timestamp_procrastinate_passes():
    bad = [
        pt.task.name
        for pt in app.periodic_registry.periodic_tasks.values()
        if not _accepts_timestamp(pt.task.func)
    ]
    assert bad == []
