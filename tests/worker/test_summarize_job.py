"""The summarize job is declared the way the night window and the worker need."""

from __future__ import annotations

import inspect
from datetime import UTC, datetime, time
from types import SimpleNamespace
from typing import Any

import pytest
from procrastinate import exceptions as procrastinate_exceptions

from techradar.worker import tasks
from techradar.worker.app import app
from techradar.worker.tasks import summarize_chapters_job


def test_summarize_job_declaration():
    assert summarize_chapters_job.name == "summarize_chapters_job"
    assert summarize_chapters_job.queue == "llm"
    assert app.tasks["summarize_chapters_job"] is summarize_chapters_job


def test_summarize_job_has_no_global_lock():
    # one global lock made every other book wait: the lock is per doc, set when deferring
    assert not summarize_chapters_job.lock


def test_night_only_gets_the_exact_task_name():
    # a wrong name would defer a job that no worker runs
    src = inspect.getsource(tasks)
    assert src.count('"summarize_chapters_job"') == 2
    assert 'task_name="summarize_chapters_job"' in src


class _Recorder:
    """Stands in for `summarize_chapters_job.configure(...)`."""

    def __init__(self, raises: Exception | None = None) -> None:
        self.raises = raises
        self.options: list[dict[str, Any]] = []
        self.deferred: list[dict[str, Any]] = []

    def configure(self, **options: Any) -> _Recorder:
        self.options.append(options)
        return self

    async def defer_async(self, **kwargs: Any) -> None:
        if self.raises is not None:
            raise self.raises
        self.deferred.append(kwargs)


@pytest.fixture
def recorder(monkeypatch: pytest.MonkeyPatch) -> _Recorder:
    rec = _Recorder()
    monkeypatch.setattr(summarize_chapters_job, "configure", rec.configure)
    monkeypatch.setattr(summarize_chapters_job, "defer_async", rec.defer_async, raising=False)
    return rec


async def test_queue_summaries_uses_a_per_doc_lock_and_queueing_lock(recorder: _Recorder):
    await tasks._queue_summaries(7)
    assert recorder.options == [{"lock": "summ:7", "queueing_lock": "summ:7"}]
    assert recorder.deferred == [{"doc_id": 7}]


async def test_queue_summaries_with_a_time_keeps_the_locks(recorder: _Recorder):
    when = datetime(2026, 11, 15, 1, 0, tzinfo=UTC)
    await tasks._queue_summaries(7, when=when)
    assert recorder.options == [{"lock": "summ:7", "queueing_lock": "summ:7", "schedule_at": when}]


async def test_two_docs_get_two_locks(recorder: _Recorder):
    await tasks._queue_summaries(1)
    await tasks._queue_summaries(2)
    assert {o["lock"] for o in recorder.options} == {"summ:1", "summ:2"}


async def test_queue_summaries_swallows_a_duplicate(monkeypatch: pytest.MonkeyPatch):
    rec = _Recorder(raises=procrastinate_exceptions.AlreadyEnqueued("dup"))
    monkeypatch.setattr(summarize_chapters_job, "configure", rec.configure)
    await tasks._queue_summaries(7)  # no exception: one is already waiting


async def test_night_only_deferral_keeps_the_per_doc_locks(recorder: _Recorder):
    # `night_only` calls this when the job starts outside the window
    when = datetime(2026, 11, 15, 1, 0, tzinfo=UTC)
    await tasks._defer_summaries(when, {"doc_id": 9})
    assert recorder.options[0]["lock"] == "summ:9"
    assert recorder.options[0]["queueing_lock"] == "summ:9"
    assert recorder.options[0]["schedule_at"] == when
    assert recorder.deferred == [{"doc_id": 9}]


def _stub_job_env(monkeypatch: pytest.MonkeyPatch, result: dict[str, int]) -> dict[str, Any]:
    seen: dict[str, Any] = {}
    settings = SimpleNamespace(
        data_dir=__import__("pathlib").Path("/nonexistent-data"),
        telegram_owner_chat_id=1,
        night_start="01:00",
        night_end="05:00",
        tz="Asia/Kolkata",
    )

    class _Session:
        async def __aenter__(self) -> _Session:
            return self

        async def __aexit__(self, *exc: object) -> None:
            return None

    async def fake_summarize_doc(session: Any, completer: Any, doc_id: int, **kw: Any):
        seen["doc_id"] = doc_id
        seen["kwargs"] = kw
        return result

    monkeypatch.setattr(tasks, "_get_settings", lambda: settings)
    monkeypatch.setattr(tasks, "load_roles", lambda *a, **k: object())
    monkeypatch.setattr(tasks, "LiteLLMCompleter", lambda *a, **k: object())
    monkeypatch.setattr(tasks, "make_session_factory", lambda *a, **k: _Session)
    monkeypatch.setattr(tasks, "summarize_doc", fake_summarize_doc)
    return seen


def _inner_job():
    return summarize_chapters_job.func.__wrapped__


async def test_job_redefers_for_the_next_window_when_chapters_remain(
    monkeypatch: pytest.MonkeyPatch, recorder: _Recorder
):
    _stub_job_env(
        monkeypatch, {"summarized": 1, "failed": 1, "skipped": 0, "given_up": 0, "more": 1}
    )
    await _inner_job()(doc_id=5)
    [opts] = recorder.options
    assert opts["lock"] == "summ:5" and opts["queueing_lock"] == "summ:5"
    when = opts["schedule_at"]
    assert when.tzinfo is not None
    local = when.astimezone(__import__("zoneinfo").ZoneInfo("Asia/Kolkata"))
    assert local.time() == time(1, 0)  # tomorrow's window start
    assert when > datetime.now(UTC)
    assert recorder.deferred == [{"doc_id": 5}]


async def test_job_does_not_redefer_when_done(monkeypatch: pytest.MonkeyPatch, recorder: _Recorder):
    _stub_job_env(
        monkeypatch, {"summarized": 3, "failed": 0, "skipped": 0, "given_up": 0, "more": 0}
    )
    await _inner_job()(doc_id=5)
    assert recorder.options == []


async def test_job_gives_summarize_doc_a_window_check(
    monkeypatch: pytest.MonkeyPatch, recorder: _Recorder
):
    seen = _stub_job_env(monkeypatch, {"summarized": 0, "failed": 0, "skipped": 0, "more": 0})
    await _inner_job()(doc_id=5)
    in_window = seen["kwargs"]["in_window"]
    assert callable(in_window)
    assert isinstance(in_window(), bool)
