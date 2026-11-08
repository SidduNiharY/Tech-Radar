"""Tests for Telegram callback query handling (Phase 2b Task 6).

SEC: SEC-26.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from techradar.bot.callbacks import handle_callback_query
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
