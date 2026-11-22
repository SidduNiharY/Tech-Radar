"""The Phase 8 (exams) background jobs: declarations and what each one does."""

from __future__ import annotations

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
