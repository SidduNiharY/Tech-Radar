"""Tests for Telegram callback query handling (Phase 2b Task 6).

SEC: SEC-26.
"""

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from techradar.bot import callbacks
from techradar.bot.callbacks import handle_callback_query
from techradar.tickets import Ticket
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


# --- quarantine (Phase 2c Task 10; release through a ticket since Phase 4 Task 2b) -----

CHAT = 123
TICKET = Ticket(
    id=77, token="b" * 32, summary="Release x?", expires_at=datetime(2026, 11, 22, tzinfo=UTC)
)


def _quarantine_ctx(user_id: int, data: str, *, gate: object = None, chat: int = CHAT):
    query = MagicMock()
    query.data = data
    query.from_user.id = user_id
    query.answer = AsyncMock()
    query.message.reply_text = AsyncMock()
    query.message.chat.id = chat
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


_ACTING = ("release_prompt", "create_ticket", "token_for", "run_confirmed", "delete_item")


@pytest.mark.parametrize("data", ["qrel:5", "qrel_ok:5", "qdel:5", "tk:77"])
async def test_stranger_quarantine_callbacks_ignored(monkeypatch, data: str) -> None:
    calls = AsyncMock()
    for name in _ACTING:
        monkeypatch.setattr(callbacks, name, calls)
    update, context, query, opened = _quarantine_ctx(999, data, gate=AsyncMock())
    await handle_callback_query(update, context)
    assert opened == [] and calls.await_count == 0
    query.answer.assert_called_once_with()
    query.message.reply_text.assert_not_called()


async def test_owner_release_creates_a_ticket_and_asks(monkeypatch) -> None:
    prompt = AsyncMock(return_value="Release x? It will be processed as flagged.")
    create = AsyncMock(return_value=TICKET)
    monkeypatch.setattr(callbacks, "release_prompt", prompt)
    monkeypatch.setattr(callbacks, "create_ticket", create)
    update, context, query, opened = _quarantine_ctx(123, "qrel:5")
    await handle_callback_query(update, context)
    assert prompt.await_args.args[1] == 5
    kw = create.await_args.kwargs
    assert (kw["session_id"], kw["channel"], kw["action"], kw["args"]) == (
        f"tg:{CHAT}",
        "telegram",
        "quarantine.release",
        {"id": 5},
    )
    assert kw["summary"] == "Release x? It will be processed as flagged."
    opened[0].commit.assert_awaited_once()
    (text,), reply_kw = query.message.reply_text.call_args
    assert text == "Release x? It will be processed as flagged."
    [[button]] = reply_kw["reply_markup"].inline_keyboard
    assert (button.text, button.callback_data) == ("Yes, release", "tk:77")


async def test_release_of_an_unknown_item_creates_no_ticket(monkeypatch) -> None:
    create = AsyncMock()
    monkeypatch.setattr(callbacks, "release_prompt", AsyncMock(return_value=None))
    monkeypatch.setattr(callbacks, "create_ticket", create)
    update, context, query, _opened = _quarantine_ctx(123, "qrel:5")
    await handle_callback_query(update, context)
    assert create.await_count == 0
    query.answer.assert_called_once_with("Nothing to release.")


async def test_confirm_runs_the_ticket_for_this_chat_and_commits(monkeypatch) -> None:
    token_for = AsyncMock(return_value=TICKET.token)
    run = AsyncMock(return_value=("ok", "Released. It will be processed as flagged."))
    monkeypatch.setattr(callbacks, "token_for", token_for)
    monkeypatch.setattr(callbacks, "run_confirmed", run)
    update, context, query, opened = _quarantine_ctx(123, "tk:77")
    await handle_callback_query(update, context)
    assert token_for.await_args.args[1:] == (77, f"tg:{CHAT}")
    assert run.await_args.args[1:3] == (TICKET.token, f"tg:{CHAT}")
    opened[0].commit.assert_awaited_once()
    query.answer.assert_called_once_with("Released. It will be processed as flagged.")


async def test_expired_confirmation_says_so(monkeypatch) -> None:
    monkeypatch.setattr(callbacks, "token_for", AsyncMock(return_value=TICKET.token))
    monkeypatch.setattr(callbacks, "run_confirmed", AsyncMock(return_value=("expired", None)))
    update, context, query, _opened = _quarantine_ctx(123, "tk:77")
    await handle_callback_query(update, context)
    query.answer.assert_called_once_with("That confirmation expired. Try again.")


@pytest.mark.parametrize("result", ["used", "wrong_session", "tampered", "cancelled", "unknown"])
async def test_other_refusals_are_one_plain_answer(monkeypatch, result: str) -> None:
    monkeypatch.setattr(callbacks, "token_for", AsyncMock(return_value=TICKET.token))
    monkeypatch.setattr(callbacks, "run_confirmed", AsyncMock(return_value=(result, None)))
    update, context, query, _opened = _quarantine_ctx(123, "tk:77")
    await handle_callback_query(update, context)
    query.answer.assert_called_once_with("That confirmation is no longer valid.")


async def test_a_ticket_of_another_chat_is_not_found(monkeypatch) -> None:
    run = AsyncMock()
    monkeypatch.setattr(callbacks, "token_for", AsyncMock(return_value=None))
    monkeypatch.setattr(callbacks, "run_confirmed", run)
    update, context, query, _opened = _quarantine_ctx(123, "tk:77", chat=-100)
    await handle_callback_query(update, context)
    assert run.await_count == 0
    query.answer.assert_called_once_with("That confirmation is no longer valid.")


async def test_old_two_step_button_releases_nothing(monkeypatch) -> None:
    calls = AsyncMock()
    for name in _ACTING:
        monkeypatch.setattr(callbacks, name, calls)
    update, context, query, opened = _quarantine_ctx(123, "qrel_ok:5")
    await handle_callback_query(update, context)
    assert calls.await_count == 0 and opened == []
    query.answer.assert_called_once_with("That button expired. Press Release again.")


async def test_owner_delete_commits(monkeypatch) -> None:
    dele = AsyncMock(return_value="deleted")
    monkeypatch.setattr(callbacks, "delete_item", dele)
    update, context, query, opened = _quarantine_ctx(123, "qdel:5")
    await handle_callback_query(update, context)
    assert dele.await_args.args[1] == 5
    assert dele.await_args.kwargs["quarantine_dir"] == Path("/data/quarantine")
    assert "library_dir" not in dele.await_args.kwargs  # worker-bulk removes originals
    opened[0].commit.assert_awaited_once()
    query.answer.assert_called_once_with("Deleted.")


@pytest.mark.parametrize("data", ["qdel:5:6", "tk:77:1", "qrel:5:6"])
async def test_quarantine_callback_with_two_ids_is_refused(monkeypatch, data: str) -> None:
    calls = AsyncMock()
    for name in _ACTING:
        monkeypatch.setattr(callbacks, name, calls)
    update, context, query, opened = _quarantine_ctx(123, data)
    await handle_callback_query(update, context)
    assert calls.await_count == 0 and opened == []
