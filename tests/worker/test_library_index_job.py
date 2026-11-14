"""The library indexing job and the bulk jobs' declarations (Phase 2c wiring)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from procrastinate import exceptions as procrastinate_exceptions

from techradar.worker import tasks
from techradar.worker.app import app


def test_index_job_declaration():
    job = tasks.index_library_chapters_job
    assert job.name == "index_library_chapters_job"
    assert job.queue == "llm"  # it needs the embedder; worker-bulk has no network to ollama
    assert app.tasks["index_library_chapters_job"] is job


def test_periodic_bulk_jobs_do_not_pile_up():
    collect, resume = tasks.collect_bulk_results_job, tasks.resume_bulk_job
    assert collect.queueing_lock and resume.queueing_lock
    assert collect.queueing_lock != resume.queueing_lock
    assert collect.queue == resume.queue == "bulk"


class _Ids:
    def __init__(self, ids: list[int]) -> None:
        self._ids = ids

    def scalars(self) -> _Ids:
        return self

    def all(self) -> list[int]:
        return self._ids


def _deps(chapter_ids: list[int]) -> SimpleNamespace:
    session = MagicMock()
    session.execute = AsyncMock(return_value=_Ids(chapter_ids))
    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=session)
    factory.return_value.__aexit__ = AsyncMock(return_value=False)
    return SimpleNamespace(session_factory=factory)


async def test_index_job_indexes_each_chapter_then_defers_summaries(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    monkeypatch.setattr(tasks, "get_index_deps", lambda: _deps([11, 12, 13]))
    index = AsyncMock(side_effect=[4, 0, 2])
    monkeypatch.setattr(tasks, "index_library_chapter", index)
    defer = AsyncMock()
    monkeypatch.setattr(tasks.summarize_chapters_job, "defer_async", defer)
    with caplog.at_level("WARNING"):
        await tasks.index_library_chapters_job(doc_id=7)
    assert [c.args[1] for c in index.await_args_list] == [11, 12, 13]
    defer.assert_awaited_once_with(doc_id=7)
    assert any("chapter 12 indexed 0 chunks" in r.getMessage() for r in caplog.records)


async def test_index_job_with_no_chapters_still_defers_summaries(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(tasks, "get_index_deps", lambda: _deps([]))
    index = AsyncMock()
    monkeypatch.setattr(tasks, "index_library_chapter", index)
    defer = AsyncMock()
    monkeypatch.setattr(tasks.summarize_chapters_job, "defer_async", defer)
    await tasks.index_library_chapters_job(doc_id=7)
    index.assert_not_awaited()
    defer.assert_awaited_once_with(doc_id=7)


async def test_queue_index_defers_one_locked_job_per_doc(monkeypatch: pytest.MonkeyPatch):
    deferrer = SimpleNamespace(defer_async=AsyncMock())
    configure = MagicMock(return_value=deferrer)
    monkeypatch.setattr(tasks.index_library_chapters_job, "configure", configure)
    await tasks._queue_index(9)
    configure.assert_called_once_with(lock="index_library_9", queueing_lock="index_library_9")
    deferrer.defer_async.assert_awaited_once_with(doc_id=9)


async def test_queue_index_accepts_a_job_that_is_already_queued(monkeypatch: pytest.MonkeyPatch):
    deferrer = SimpleNamespace(
        defer_async=AsyncMock(side_effect=procrastinate_exceptions.AlreadyEnqueued("x"))
    )
    monkeypatch.setattr(
        tasks.index_library_chapters_job, "configure", MagicMock(return_value=deferrer)
    )
    await tasks._queue_index(9)  # no exception
