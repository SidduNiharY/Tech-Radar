"""Tests for Telegram callback query handling (Phase 2b Task 6).

SEC: SEC-26.
"""

from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from techradar.bot import callbacks
from techradar.bot.callbacks import handle_callback_query
from techradar.library.quarantine import ReleaseRequests
from techradar.messaging.outbox import Button
from techradar.worker.names import SAVE_ANSWER


@pytest.mark.asyncio
async def test_owner_save_answer_defers_task() -> None:
    query = MagicMock()
    query.data = "save_answer:42"
    query.from_user.id = 123
    query.answer = AsyncMock()

    update = MagicMock()
    update.callback_query = query

    proc_app = MagicMock()
    task_mock = MagicMock()
    task_mock.defer_async = AsyncMock()
    proc_app.configure_task.return_value = task_mock

    context = MagicMock()
    context.application.bot_data = {
        "owner_id": 123,
        "procrastinate_app": proc_app,
    }

    await handle_callback_query(update, context)

    proc_app.configure_task.assert_called_once_with(name=SAVE_ANSWER)
    task_mock.defer_async.assert_called_once_with(answer_id=42)
    query.answer.assert_called_once_with("Saving to vault...")


@pytest.mark.asyncio
async def test_stranger_callback_ignored() -> None:
    query = MagicMock()
    query.data = "save_answer:42"
    query.from_user.id = 999  # Stranger
    query.answer = AsyncMock()

    update = MagicMock()
    update.callback_query = query

    proc_app = MagicMock()
    context = MagicMock()
    context.application.bot_data = {
        "owner_id": 123,
        "procrastinate_app": proc_app,
    }

    await handle_callback_query(update, context)

    proc_app.configure_task.assert_not_called()
    query.answer.assert_called_once_with()


@pytest.mark.asyncio
async def test_invalid_callback_data_answered_with_error() -> None:
    query = MagicMock()
    query.data = "invalid:format:too:many:args"
    query.from_user.id = 123
    query.answer = AsyncMock()

    update = MagicMock()
    update.callback_query = query

    context = MagicMock()
    context.application.bot_data = {"owner_id": 123}

    await handle_callback_query(update, context)
    query.answer.assert_called_once_with("Invalid request.")


# --- quarantine (Phase 2c Task 10) ------------------------------------------------


def _quarantine_ctx(user_id: int, data: str, *, gate: object = None):
    query = MagicMock()
    query.data = data
    query.from_user.id = user_id
    query.answer = AsyncMock()
    query.message.reply_text = AsyncMock()
    update = MagicMock()
    update.callback_query = query

    session = MagicMock()
    session.commit = AsyncMock()
    opened: list[object] = []

    @asynccontextmanager
    async def factory():
        opened.append(session)
        yield session

    context = MagicMock()
    context.application.bot_data = {
        "owner_id": 123,
        "session_factory": factory,
        "quarantine_dir": "/data/quarantine",
    }
    if gate is not None:
        context.application.bot_data["release_gate"] = gate
    return update, context, query, opened


@pytest.mark.parametrize("data", ["qrel:5", "qrel_ok:5", "qdel:5"])
async def test_stranger_quarantine_callbacks_ignored(monkeypatch, data: str) -> None:
    calls = AsyncMock()
    for name in ("request_release", "confirm_release", "delete_item"):
        monkeypatch.setattr(callbacks, name, calls)
    update, context, query, opened = _quarantine_ctx(999, data, gate=AsyncMock())
    await handle_callback_query(update, context)
    assert opened == [] and calls.await_count == 0
    query.answer.assert_called_once_with()
    query.message.reply_text.assert_not_called()


async def test_owner_release_asks_for_confirmation(monkeypatch) -> None:
    prompt = ("Release x?", [[Button(text="Yes, release", data="qrel_ok:5")]])
    req = AsyncMock(return_value=prompt)
    monkeypatch.setattr(callbacks, "request_release", req)
    update, context, query, opened = _quarantine_ctx(123, "qrel:5")
    await handle_callback_query(update, context)
    assert req.await_args.args[1] == 5
    assert isinstance(req.await_args.kwargs["requests"], ReleaseRequests)
    (text,), kw = query.message.reply_text.call_args
    assert text == "Release x?"
    markup = kw["reply_markup"].inline_keyboard
    assert markup[0][0].callback_data == "qrel_ok:5"
    # The request store is kept, so the confirm can find it.
    assert context.application.bot_data["quarantine_requests"] is req.await_args.kwargs["requests"]


async def test_owner_confirm_releases_and_commits(monkeypatch) -> None:
    gate = AsyncMock()
    conf = AsyncMock(return_value="released")
    monkeypatch.setattr(callbacks, "confirm_release", conf)
    update, context, query, opened = _quarantine_ctx(123, "qrel_ok:5", gate=gate)
    await handle_callback_query(update, context)
    assert conf.await_args.args[1] == 5 and conf.await_args.kwargs["gate"] is gate
    opened[0].commit.assert_awaited_once()
    query.answer.assert_called_once()
    assert "flagged" in query.answer.call_args.args[0]


async def test_confirm_without_gate_still_releases_library_docs(monkeypatch) -> None:
    """The bot runs no gate: library docs are re-gated by the parser, others are refused."""
    conf = AsyncMock(return_value="released")
    monkeypatch.setattr(callbacks, "confirm_release", conf)
    update, context, query, opened = _quarantine_ctx(123, "qrel_ok:5")
    await handle_callback_query(update, context)
    assert conf.await_args.kwargs["gate"] is None
    opened[0].commit.assert_awaited_once()


async def test_stranger_confirm_without_gate_is_ignored(monkeypatch) -> None:
    conf = AsyncMock()
    monkeypatch.setattr(callbacks, "confirm_release", conf)
    update, context, query, opened = _quarantine_ctx(999, "qrel_ok:5")
    await handle_callback_query(update, context)
    assert conf.await_count == 0 and opened == []


async def test_owner_delete_commits(monkeypatch) -> None:
    dele = AsyncMock(return_value="deleted")
    monkeypatch.setattr(callbacks, "delete_item", dele)
    update, context, query, opened = _quarantine_ctx(123, "qdel:5")
    await handle_callback_query(update, context)
    assert dele.await_args.args[1] == 5
    assert dele.await_args.kwargs["quarantine_dir"] == Path("/data/quarantine")
    opened[0].commit.assert_awaited_once()
    query.answer.assert_called_once_with("Deleted.")


async def test_quarantine_callback_with_two_ids_is_refused(monkeypatch) -> None:
    calls = AsyncMock()
    monkeypatch.setattr(callbacks, "delete_item", calls)
    update, context, query, opened = _quarantine_ctx(123, "qdel:5:6")
    await handle_callback_query(update, context)
    assert calls.await_count == 0 and opened == []
