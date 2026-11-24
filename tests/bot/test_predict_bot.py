"""Bot side of the predictions log: routing, /predict, the buttons and replies (SEC-26)."""

from __future__ import annotations

import re
from contextlib import asynccontextmanager
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from techradar.bot import callbacks, predict
from techradar.bot.routing import Routed, route_update
from techradar.messaging.outbox import parse_callback
from techradar.world.predictions import reminder_buttons

OWNER = 42


def test_predict_is_the_owners_alone() -> None:
    assert route_update(OWNER, "/predict Rates fall by 2027-03-31", OWNER) == Routed(
        "predict", "Rates fall by 2027-03-31"
    )
    assert route_update(OWNER, "/predict@bot x by 2027-01-01", OWNER).action == "predict"
    assert route_update(7, "/predict x by 2027-01-01", OWNER) == Routed("ignore")
    # a study group the owner approved may use the bot, but never the owner's log
    assert route_update(-100, "/predict x by 2027-01-01", OWNER, group_ids={-100}) == Routed(
        "ignore"
    )


def test_reply_to_a_reminder_routes_only_for_the_owner() -> None:
    kw = {"reply_to_message_id": 9, "prediction_message_ids": {9}}
    assert route_update(OWNER, "They did fall", OWNER, **kw) == Routed(
        "prediction_reply", "They did fall"
    )
    assert route_update(7, "They did fall", OWNER, **kw) == Routed("ignore")
    assert route_update(-100, "x", OWNER, group_ids={-100}, **kw) == Routed("ignore")
    assert route_update(
        OWNER, "They did", OWNER, reply_to_message_id=8, **{"prediction_message_ids": {9}}
    ) == Routed("ignore")
    assert route_update(OWNER, "/status", OWNER, **kw) == Routed("status")


def test_button_data_fits_the_callback_pattern() -> None:
    pattern = re.compile(r"^[a-z_]{1,20}(:[0-9]{1,12}){1,2}$")
    for b in reminder_buttons(999_999_999_999)[0]:
        assert pattern.match(b.data) and parse_callback(b.data) is not None


def _factory(session: MagicMock):
    @asynccontextmanager
    async def factory():
        yield session

    return factory


def _session() -> MagicMock:
    s = MagicMock()
    s.commit = AsyncMock()
    return s


def _update() -> MagicMock:
    u = MagicMock()
    u.message.reply_text = AsyncMock()
    return u


def _bot_data(session: MagicMock, proc: MagicMock | None = None) -> dict:
    return {"owner_id": OWNER, "session_factory": _factory(session), "procrastinate_app": proc}


def _proc() -> MagicMock:
    proc = MagicMock()
    task = MagicMock()
    task.defer_async = AsyncMock()
    proc.configure_task.return_value = task
    return proc


async def test_predict_saves_and_queues_the_page_update(monkeypatch: pytest.MonkeyPatch) -> None:
    record = AsyncMock(return_value=1)
    monkeypatch.setattr(predict, "record_prediction", record)
    session, proc, update = _session(), _proc(), _update()
    await predict.handle_predict(
        update, _bot_data(session, proc), "Rates fall by 2027-03-31", today=date(2026, 11, 8)
    )
    record.assert_awaited_once_with(session, "Rates fall", date(2027, 3, 31))
    session.commit.assert_awaited_once()
    proc.configure_task.assert_called_once_with(name="predictions_sync_job")
    assert update.message.reply_text.call_args.args[0] == "Saved. I'll ask you on 31 Mar 2027."


async def test_bad_predict_saves_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    record = AsyncMock()
    monkeypatch.setattr(predict, "record_prediction", record)
    update, session = _update(), _session()
    await predict.handle_predict(update, _bot_data(session), "Rates fall", today=date(2026, 11, 8))
    record.assert_not_awaited()
    assert update.message.reply_text.call_args.args[0].startswith("Use: /predict")


async def test_outcome_button_records_for_the_owner_only(monkeypatch: pytest.MonkeyPatch) -> None:
    record = AsyncMock(return_value=True)
    monkeypatch.setattr(predict, "record_outcome", record)

    def query(user_id: int, chat_id: int, data: str) -> MagicMock:
        q = MagicMock()
        q.data = data
        q.from_user.id = user_id
        q.message.chat.id = chat_id
        q.answer = AsyncMock()
        return q

    session, proc = _session(), _proc()
    ctx = MagicMock()
    ctx.application.bot_data = _bot_data(session, proc)

    stranger = query(7, 7, "pred:5:1")
    await callbacks.handle_callback_query(SimpleNamespace(callback_query=stranger), ctx)
    record.assert_not_awaited()

    wrong_chat = query(OWNER, -100, "pred:5:1")  # owner's id, but a group chat
    await callbacks.handle_callback_query(SimpleNamespace(callback_query=wrong_chat), ctx)
    record.assert_not_awaited()

    for bad in ("pred:5:9", "pred:5", "pred:0:1"):
        q = query(OWNER, OWNER, bad)
        await callbacks.handle_callback_query(SimpleNamespace(callback_query=q), ctx)
    record.assert_not_awaited()

    ok = query(OWNER, OWNER, "pred:5:2")
    await callbacks.handle_callback_query(SimpleNamespace(callback_query=ok), ctx)
    record.assert_awaited_once_with(session, 5, 2)
    assert "Wrong" in ok.answer.call_args.args[0]


async def test_reply_saves_the_words(monkeypatch: pytest.MonkeyPatch) -> None:
    save = AsyncMock(return_value=True)
    monkeypatch.setattr(predict, "set_outcome_text", save)
    update, session = _update(), _session()
    await predict.handle_prediction_reply(update, _bot_data(session, _proc()), 5, "It fell")
    save.assert_awaited_once_with(session, 5, "It fell")
    assert update.message.reply_text.call_args.args[0] == "Noted."
