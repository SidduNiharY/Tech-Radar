"""Intake-door jobs: owner links and files (Phase 3 Task 3), voice notes (Phase 6 Task 1)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from techradar.worker import tasks
from techradar.worker.app import app


def _patch(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, allowlist: Path) -> MagicMock:
    session = MagicMock()
    session.commit = AsyncMock()
    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=session)
    factory.return_value.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(tasks, "make_session_factory", MagicMock(return_value=factory))
    monkeypatch.setattr(
        tasks,
        "_get_settings",
        lambda: SimpleNamespace(
            telegram_owner_chat_id=42, data_dir=tmp_path, squid_allowlist=allowlist
        ),
    )
    return session


def test_declarations() -> None:
    assert app.tasks["owner_link"] is tasks.owner_link_job
    assert app.tasks["owner_file"] is tasks.owner_file_job
    assert tasks.owner_link_job.queue == "io" and tasks.owner_file_job.queue == "io"
    assert app.tasks["analyse_voice"] is tasks.analyse_voice_job
    assert tasks.analyse_voice_job.queue == "voice"
    assert app.tasks["cleanup_voice_job"] is tasks.cleanup_voice_job
    assert tasks.cleanup_voice_job.queue == "io" and tasks.cleanup_voice_job.queueing_lock
    periodic = {n for (n, _), _p in app.periodic_registry.periodic_tasks.items()}
    assert "cleanup_voice_job" in periodic


async def test_owner_link_job_checks_against_the_squid_allowlist(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    allowlist = tmp_path / "allowlist.txt"
    allowlist.write_text("# comment\n.pib.gov.in\n")
    session = _patch(monkeypatch, tmp_path, allowlist)
    intake = AsyncMock(return_value="Queued.")
    send = AsyncMock()
    monkeypatch.setattr(tasks, "intake_link", intake)
    monkeypatch.setattr(tasks, "enqueue_message", send)
    await tasks.owner_link_job(url="https://pib.gov.in/x")
    assert intake.await_args.args[1:] == ("https://pib.gov.in/x", frozenset({".pib.gov.in"}))
    assert send.await_args.kwargs["chat_id"] == 42 and send.await_args.kwargs["text"] == "Queued."
    session.commit.assert_awaited_once()


async def test_owner_link_job_fails_closed_without_an_allowlist(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch(monkeypatch, tmp_path, tmp_path / "missing.txt")
    intake = AsyncMock()
    send = AsyncMock()
    monkeypatch.setattr(tasks, "intake_link", intake)
    monkeypatch.setattr(tasks, "enqueue_message", send)
    await tasks.owner_link_job(url="https://pib.gov.in/x")
    intake.assert_not_called()
    assert send.await_args.kwargs["text"] == "Not available yet."


async def test_owner_file_job_uses_the_drop_raw_and_jobs_folders(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch(monkeypatch, tmp_path, tmp_path / "a.txt")
    take = AsyncMock(return_value="queued")
    send = AsyncMock()
    monkeypatch.setattr(tasks, "take_owner_file", take)
    monkeypatch.setattr(tasks, "enqueue_message", send)
    await tasks.owner_file_job(name="a" * 64 + ".pdf")
    args = take.await_args.args
    assert args[1:] == (
        "a" * 64 + ".pdf",
        tmp_path / "telegram-in",
        tmp_path / "raw",
        tmp_path / "parse-jobs",
    )
    send.assert_not_called()  # the bot already said "Queued."


async def test_owner_file_job_tells_the_owner_when_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch(monkeypatch, tmp_path, tmp_path / "a.txt")
    monkeypatch.setattr(tasks, "take_owner_file", AsyncMock(return_value="refused"))
    send = AsyncMock()
    monkeypatch.setattr(tasks, "enqueue_message", send)
    await tasks.owner_file_job(name="x")
    assert send.await_args.kwargs["text"] == "Couldn't take that file."


async def test_analyse_voice_job_without_a_transcriber_tells_the_owner(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    session = _patch(monkeypatch, tmp_path, tmp_path / "a.txt")
    mark = AsyncMock(return_value=True)
    send = AsyncMock()
    monkeypatch.setattr(tasks, "mark_voice_unavailable", mark)
    monkeypatch.setattr(tasks, "enqueue_message", send)
    await tasks.analyse_voice_job(session_id=7)
    assert mark.await_args.args[1] == 7
    assert send.await_args.kwargs["text"] == tasks.VOICE_UNAVAILABLE_REPLY
    session.commit.assert_awaited_once()


async def test_analyse_voice_job_for_a_missing_session_says_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch(monkeypatch, tmp_path, tmp_path / "a.txt")
    monkeypatch.setattr(tasks, "mark_voice_unavailable", AsyncMock(return_value=False))
    send = AsyncMock()
    monkeypatch.setattr(tasks, "enqueue_message", send)
    await tasks.analyse_voice_job(session_id=7)
    send.assert_not_called()


async def test_cleanup_voice_job_is_limited_to_the_voice_folder(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch(monkeypatch, tmp_path, tmp_path / "a.txt")
    cleanup = AsyncMock(return_value=0)
    monkeypatch.setattr(tasks, "cleanup_voice", cleanup)
    await tasks.cleanup_voice_job(timestamp=1)
    assert cleanup.await_args.kwargs["voice_dir"] == tmp_path / "voice"
