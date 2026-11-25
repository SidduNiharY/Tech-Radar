"""The Phase 6 jobs in worker/tasks.py: names, queues, schedules and the timestamp argument."""

from __future__ import annotations

import inspect

from techradar.worker import tasks
from techradar.worker.app import app
from techradar.worker.names import ESSAY_REPLY, NIGHT_QUEUE, POLISH, REFLECTION_SAVE

PERIODIC = {
    "essay_prompt_job": "30 4 * * 6",
    "reading_quiz_job": "30 12 * * 5",
    "reflection_prompt_job": "30 14 * * 0",
}


def _task(name: str):
    return app.tasks[name]


def test_periodic_english_jobs_have_their_schedule_and_timestamp() -> None:
    crons = {pt.task.name: pt.cron for pt in app.periodic_registry.periodic_tasks.values()}
    for name, cron in PERIODIC.items():
        assert crons[name] == cron
        assert "timestamp" in inspect.signature(getattr(tasks, name).func).parameters


def test_on_demand_english_jobs_are_registered() -> None:
    for name in (POLISH, ESSAY_REPLY, REFLECTION_SAVE):
        assert name in app.tasks


def test_no_phase6_job_runs_on_the_night_queue_by_accident() -> None:
    for name in [*PERIODIC, POLISH, ESSAY_REPLY, REFLECTION_SAVE]:
        assert _task(name).queue != NIGHT_QUEUE


def test_english_reminder_runs_every_15_minutes() -> None:
    crons = {pt.task.name: pt.cron for pt in app.periodic_registry.periodic_tasks.values()}
    assert crons["english_reminder_job"] == "*/15 * * * *"
    assert "timestamp" in inspect.signature(tasks.english_reminder_job.func).parameters
