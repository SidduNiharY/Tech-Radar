"""Phase 3 jobs: declared as planned, and each is a thin wrapper (session, run_*, commit)."""

from __future__ import annotations

from datetime import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from techradar.worker import tasks
from techradar.worker.app import app


def _session_factory() -> tuple[MagicMock, MagicMock]:
    session = MagicMock()
    session.commit = AsyncMock()
    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=session)
    factory.return_value.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=factory), session


def _patch(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    make, session = _session_factory()
    monkeypatch.setattr(tasks, "make_session_factory", make)
    monkeypatch.setattr(
        tasks,
        "_get_settings",
        lambda: SimpleNamespace(
            tz="Asia/Kolkata",
            telegram_owner_chat_id=42,
            briefing_time="06:30",
            misfire_grace_s=21600,
            data_dir=tasks.Path("/data"),
        ),
    )
    return session


def test_briefing_job_declaration():
    job = tasks.briefing_job
    assert job.name == "briefing_job" and job.queue == "io"
    assert job.queueing_lock  # a slow run is not joined by duplicates
    assert app.tasks["briefing_job"] is job


async def test_briefing_job_runs_and_commits(monkeypatch: pytest.MonkeyPatch):
    session = _patch(monkeypatch)
    run = AsyncMock()
    monkeypatch.setattr(tasks, "run_briefing", run)
    await tasks.briefing_job()
    run.assert_awaited_once()
    kwargs = run.await_args.kwargs
    assert kwargs["owner_chat_id"] == 42 and kwargs["at_time"] == time(6, 30)
    assert kwargs["grace_s"] == 21600
    assert kwargs["now"].utcoffset().total_seconds() == 19800  # local time, not UTC
    session.commit.assert_awaited_once()


async def test_save_take_job_saves_and_confirms(monkeypatch: pytest.MonkeyPatch):
    session = _patch(monkeypatch)
    monkeypatch.setattr(tasks, "save_take", AsyncMock(return_value="saved"))
    send = AsyncMock()
    monkeypatch.setattr(tasks, "enqueue_message", send)
    await tasks.save_take_job(briefing_id=3, text="Rates will fall")
    assert send.await_args.kwargs["text"] == "Saved your take."
    assert send.await_args.kwargs["chat_id"] == 42
    session.commit.assert_awaited_once()
    assert app.tasks["save_take"] is tasks.save_take_job


def test_make_mcqs_job_is_nightly_on_the_llm_queue():
    job = tasks.make_mcqs_job
    assert job.name == "make_mcqs_job" and job.queue == "llm" and job.queueing_lock
    assert app.tasks["make_mcqs_job"] is job


async def test_make_mcqs_job_runs_and_commits(monkeypatch: pytest.MonkeyPatch):
    session = _patch(monkeypatch)
    run = AsyncMock()
    monkeypatch.setattr(tasks, "run_make_mcqs", run)
    monkeypatch.setattr(tasks, "_completer", lambda: "completer")
    await tasks.make_mcqs_job()
    assert run.await_args.args[1] == "completer"
    session.commit.assert_awaited_once()


def test_quiz_cards_and_mistakes_jobs_are_declared():
    assert tasks.quiz_job.name == "quiz" and tasks.quiz_job.queue == "io"
    assert tasks.cards_job.name == "cards" and tasks.cards_job.queue == "io"
    page = tasks.mistakes_page_job
    assert page.name == "mistakes_page" and page.queueing_lock
    for name in ("quiz", "cards", "mistakes_page"):
        assert name in app.tasks


async def test_quiz_and_cards_jobs_pass_the_daily_limits(monkeypatch: pytest.MonkeyPatch):
    session = _patch(monkeypatch)
    monkeypatch.setattr(
        tasks,
        "_get_settings",
        lambda: SimpleNamespace(
            tz="Asia/Kolkata",
            telegram_owner_chat_id=42,
            daily_new_cards=10,
            daily_reviews=40,
        ),
    )
    quiz, cards = AsyncMock(), AsyncMock()
    monkeypatch.setattr(tasks, "run_quiz", quiz)
    monkeypatch.setattr(tasks, "run_cards", cards)
    await tasks.quiz_job()
    await tasks.cards_job()
    assert quiz.await_args.kwargs["limit"] == 10 and quiz.await_args.kwargs["owner_chat_id"] == 42
    assert (
        cards.await_args.kwargs["new_limit"] == 10 and cards.await_args.kwargs["review_limit"] == 40
    )
    assert session.commit.await_count == 2


async def test_make_chapter_cards_job_runs_and_commits(monkeypatch: pytest.MonkeyPatch):
    session = _patch(monkeypatch)
    run = AsyncMock()
    monkeypatch.setattr(tasks, "run_make_chapter_cards", run)
    monkeypatch.setattr(tasks, "_completer", lambda: "completer")
    await tasks.make_chapter_cards_job(chapter_id=11)
    assert run.await_args.args[1:3] == ("completer", 11)
    assert run.await_args.kwargs["owner_chat_id"] == 42
    assert tasks.make_chapter_cards_job.queue == "llm"
    session.commit.assert_awaited_once()
