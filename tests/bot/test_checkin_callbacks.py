"""Check-in button taps (Phase 5 Task 2). SEC-26: owner only, owner's chat only."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest

from techradar.bot import planner_commands
from techradar.bot.callbacks import handle_callback_query
from techradar.messaging.outbox import parse_callback
from techradar.planner.checkin import checkin_keyboard


def test_every_checkin_button_matches_the_callback_pattern():
    for row in checkin_keyboard():
        for button in row:
            assert parse_callback(button.data) is not None


def _ctx(user_id: int, data: str, chat_id: int = 123):
    query = MagicMock()
    query.data = data
    query.from_user.id = user_id
    query.message.chat.id = chat_id
    query.answer = AsyncMock()
    update = MagicMock()
    update.callback_query = query
    session = MagicMock()
    session.commit = AsyncMock()

    @asynccontextmanager
    async def factory():
        yield session

    context = MagicMock()
    context.application.bot_data = {"owner_id": 123, "session_factory": factory}
    return update, context, query, session


@pytest.mark.parametrize("data", ["sleep:3", "energy:5", "mood:1"])
async def test_owner_tap_is_recorded(monkeypatch, data):
    recorded = []

    async def fake_record(session, day, field, value):
        recorded.append((field, value))

    monkeypatch.setattr(planner_commands, "record_checkin", fake_record)
    update, context, query, session = _ctx(123, data)
    await handle_callback_query(update, context)
    field, value = data.split(":")
    assert recorded == [(field, int(value))]
    session.commit.assert_awaited_once()
    query.answer.assert_called_once_with("Noted.")


@pytest.mark.parametrize("data", ["sleep:3", "energy:5", "mood:1"])
async def test_stranger_tap_is_ignored(monkeypatch, data):
    monkeypatch.setattr(planner_commands, "record_checkin", AsyncMock(side_effect=AssertionError))
    update, context, query, session = _ctx(999, data)
    await handle_callback_query(update, context)
    query.answer.assert_called_once_with()
    session.commit.assert_not_called()


async def test_owner_tap_from_another_chat_is_refused(monkeypatch):
    monkeypatch.setattr(planner_commands, "record_checkin", AsyncMock(side_effect=AssertionError))
    update, context, query, _ = _ctx(123, "mood:2", chat_id=555)
    await handle_callback_query(update, context)
    query.answer.assert_called_once_with("Invalid request.")


async def test_out_of_range_tap_is_refused():
    update, context, query, _ = _ctx(123, "mood:9")
    await handle_callback_query(update, context)
    query.answer.assert_called_once_with("Invalid request.")
