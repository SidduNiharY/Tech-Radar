"""The summarize job is declared the way the night window and the worker need."""

from __future__ import annotations

import inspect

from techradar.worker import tasks
from techradar.worker.app import app
from techradar.worker.tasks import summarize_chapters_job


def test_summarize_job_declaration():
    assert summarize_chapters_job.name == "summarize_chapters_job"
    assert summarize_chapters_job.queue == "llm"
    assert summarize_chapters_job.lock  # two runs never overlap
    assert app.tasks["summarize_chapters_job"] is summarize_chapters_job


def test_night_only_gets_the_exact_task_name():
    # a wrong name would defer a job that no worker runs
    src = inspect.getsource(tasks)
    assert src.count('"summarize_chapters_job"') == 2
    assert 'night_only(task_name="summarize_chapters_job")' in src
