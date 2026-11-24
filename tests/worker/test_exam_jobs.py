"""The Phase 8 (exams) background jobs: declarations and what each one does."""

from __future__ import annotations

import inspect
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from techradar.worker import tasks
from techradar.worker.app import app


def _factory(session: MagicMock) -> MagicMock:
    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=session)
    factory.return_value.__aexit__ = AsyncMock(return_value=False)
    return factory


def _session() -> MagicMock:
    session = MagicMock()
    session.commit = AsyncMock()
    return session


def test_syllabus_sync_job_declaration():
    job = tasks.syllabus_sync_job
    assert job.name == "syllabus_sync_job"
    assert job.queue == "io"
    assert job.queueing_lock  # a slow run never piles up copies
    assert app.tasks["syllabus_sync_job"] is job
    assert ("syllabus_sync_job", "") in app.periodic_registry.periodic_tasks  # daily


def test_suggest_topic_sources_job_declaration():
    job = tasks.suggest_topic_sources_job
    assert job.name == "suggest_topic_sources_job"
    assert job.queue == "llm"  # it needs the models on ollama
    assert job.queueing_lock
    assert app.tasks["suggest_topic_sources_job"] is job
    assert ("suggest_topic_sources_job", "") in app.periodic_registry.periodic_tasks  # nightly


def test_suggest_topic_sources_job_runs_only_in_the_night_window():
    # a wrong task name would defer a job that no worker runs
    src = inspect.getsource(tasks)
    assert 'task_name="suggest_topic_sources_job"' in src
    assert src.count('"suggest_topic_sources_job"') == 2  # the task name, and night_only's


def test_sources_digest_job_declaration():
    job = tasks.sources_digest_job
    assert job.name == "sources_digest_job"
    assert job.queue == "io"
    assert job.queueing_lock
    assert app.tasks["sources_digest_job"] is job
    assert ("sources_digest_job", "") in app.periodic_registry.periodic_tasks  # Sundays


async def test_suggest_topic_sources_job_passes_the_vault_and_commits(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    session = _session()
    run = AsyncMock(return_value=3)
    completer, embedder = object(), object()
    monkeypatch.setattr(tasks, "_get_settings", lambda: SimpleNamespace(data_dir=tmp_path))
    monkeypatch.setattr(tasks, "_exam_models", lambda: (completer, embedder))
    monkeypatch.setattr(tasks, "make_session_factory", lambda role, settings: _factory(session))
    monkeypatch.setattr(tasks, "run_suggest_topic_sources", run)

    inner = tasks.suggest_topic_sources_job.func.__wrapped__  # without the night-window check
    await inner(timestamp=1_700_000_000)

    assert run.await_args.args == (session, embedder, completer)
    assert run.await_args.kwargs["vault_root"] == tmp_path / "vault"
    session.commit.assert_awaited_once()


async def test_sources_digest_job_goes_to_the_owner_only(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    session = _session()
    digest = AsyncMock(return_value=4)
    settings = SimpleNamespace(data_dir=tmp_path, telegram_owner_chat_id=4242)
    monkeypatch.setattr(tasks, "_get_settings", lambda: settings)
    monkeypatch.setattr(tasks, "make_session_factory", lambda role, s: _factory(session))
    monkeypatch.setattr(tasks, "enqueue_sources_digest", digest)

    await tasks.sources_digest_job(timestamp=1_700_000_000)

    digest.assert_awaited_once_with(session, 4242)
    session.commit.assert_awaited_once()


def test_exam_imports_job_declaration():
    job = tasks.exam_imports_job
    assert job.name == "exam_imports_job"
    assert job.queue == "io"
    assert job.queueing_lock
    assert ("exam_imports_job", "") in app.periodic_registry.periodic_tasks


async def test_exam_imports_job_reads_the_library_inbox(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    session = _session()
    imp = AsyncMock(return_value=(2, 5))
    official = frozenset({"ssc.gov.in"})
    monkeypatch.setattr(tasks, "_get_settings", lambda: SimpleNamespace(data_dir=tmp_path))
    monkeypatch.setattr(tasks, "make_session_factory", lambda role, s: _factory(session))
    monkeypatch.setattr(tasks, "_official_domains", lambda: official)
    monkeypatch.setattr(tasks, "import_inbox_files", imp)

    await tasks.exam_imports_job(timestamp=1_700_000_000)

    imp.assert_awaited_once_with(session, tmp_path / "library-inbox", official)
    session.commit.assert_awaited_once()


def test_formula_sheets_job_declaration():
    job = tasks.formula_sheets_job
    assert job.name == "formula_sheets_job"
    assert job.queue == "llm"  # it asks the model through the RAG answer
    assert job.queueing_lock
    assert ("formula_sheets_job", "") in app.periodic_registry.periodic_tasks
    assert 'task_name="formula_sheets_job"' in inspect.getsource(tasks)


async def test_formula_sheets_job_uses_the_local_day_and_the_vault(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    session = _session()
    run = AsyncMock(return_value={"written": 2})
    deps = object()
    settings = SimpleNamespace(data_dir=tmp_path, tz="Asia/Kolkata")
    monkeypatch.setattr(tasks, "_get_settings", lambda: settings)
    monkeypatch.setattr(tasks, "make_session_factory", lambda role, s: _factory(session))
    monkeypatch.setattr(tasks, "get_rag_deps", lambda: deps)
    monkeypatch.setattr(tasks, "run_formula_sheets", run)

    await tasks.formula_sheets_job.func.__wrapped__(timestamp=1_700_000_000)

    args = run.await_args.args
    assert args[0] is session and args[1] is deps and args[2] == tmp_path / "vault"
    assert isinstance(args[3], date)


def test_library_intake_leaves_the_csv_folders_alone():
    from techradar.library.inbox import SKIPPED_DIRS

    assert {"cutoffs", "weightage", "gate"} <= SKIPPED_DIRS


async def test_syllabus_sync_job_reads_the_vault_and_commits(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    session = _session()
    sync = AsyncMock(return_value=7)
    monkeypatch.setattr(tasks, "_get_settings", lambda: SimpleNamespace(data_dir=tmp_path))
    monkeypatch.setattr(tasks, "make_session_factory", lambda role, settings: _factory(session))
    monkeypatch.setattr(tasks, "sync_syllabus", sync)

    await tasks.syllabus_sync_job(timestamp=1_700_000_000)  # procrastinate passes it

    sync.assert_awaited_once_with(session, tmp_path / "vault")
    session.commit.assert_awaited_once()
