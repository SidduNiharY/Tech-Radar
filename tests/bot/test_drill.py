"""/drill routing and the `drill:<n>:<0-3>` buttons (Phase 8 Task 4). SEC: SEC-26."""

from __future__ import annotations

from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from techradar.bot import drill
from techradar.bot.callbacks import handle_callback_query
from techradar.bot.routing import Routed, route_update
from techradar.exams.deliver import DrillOutcome

OWNER = 123
SENT = datetime(2026, 11, 21, 19, 0, tzinfo=UTC)  # 00:30 on 22 Nov in Asia/Kolkata


def test_route_drill_owner_only():
    assert route_update(42, "/drill", 42) == Routed("drill")
    assert route_update(42, "/drill@TechBot", 42) == Routed("drill")
    assert route_update(7, "/drill", 42) == Routed("ignore")  # a stranger
    assert route_update(-100, "/drill", 42, group_ids=frozenset({-100})) == Routed("ignore")


def _factory(session: MagicMock) -> MagicMock:
    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=session)
    factory.return_value.__aexit__ = AsyncMock(return_value=False)
    return factory


def _query(data: str, *, user: int = OWNER, chat: int = OWNER) -> MagicMock:
    q = MagicMock()
    q.data = data
    q.from_user.id = user
    q.answer = AsyncMock()
    q.edit_message_reply_markup = AsyncMock()
    q.message.chat.id = chat
    q.message.date = SENT
    q.message.reply_text = AsyncMock()
    return q


def _ctx(session: MagicMock) -> MagicMock:
    c = MagicMock()
    c.application.bot_data = {
        "owner_id": OWNER,
        "session_factory": _factory(session),
        "tz": "Asia/Kolkata",
    }
    return c


@pytest.mark.parametrize("data", ["drill:0:1", "drill:19:3", "drill:20:0", "drill:0:9"])
async def test_stranger_drill_tap_does_nothing(data: str, monkeypatch: pytest.MonkeyPatch):
    record = AsyncMock()
    monkeypatch.setattr(drill, "record_drill", record)
    q = _query(data, user=999)
    await handle_callback_query(SimpleNamespace(callback_query=q), _ctx(MagicMock()))  # type: ignore[arg-type]
    record.assert_not_called()
    q.answer.assert_awaited_once_with()


@pytest.mark.parametrize("data", ["drill:20:0", "drill:0:4", "drill:5"])
async def test_out_of_range_tap_is_invalid(data: str, monkeypatch: pytest.MonkeyPatch):
    record = AsyncMock()
    monkeypatch.setattr(drill, "record_drill", record)
    q = _query(data)
    await handle_callback_query(SimpleNamespace(callback_query=q), _ctx(MagicMock()))  # type: ignore[arg-type]
    record.assert_not_called()
    q.answer.assert_awaited_once_with("Invalid request.")


async def test_tap_in_a_group_is_refused(monkeypatch: pytest.MonkeyPatch):
    record = AsyncMock()
    monkeypatch.setattr(drill, "record_drill", record)
    q = _query("drill:0:1", chat=-100555)
    await handle_callback_query(SimpleNamespace(callback_query=q), _ctx(MagicMock()))  # type: ignore[arg-type]
    record.assert_not_called()


async def test_answer_is_recorded_for_the_message_day_and_timed_from_it(
    monkeypatch: pytest.MonkeyPatch,
):
    session = MagicMock()
    session.commit = AsyncMock()
    outcome = DrillOutcome(
        correct=False, explanation="2 + 2 = 4", seconds=9.0, chosen="5", answer_option="4"
    )
    record = AsyncMock(return_value=outcome)
    monkeypatch.setattr(drill, "record_drill", record)
    monkeypatch.setattr(drill, "next_unanswered", AsyncMock(return_value=None))
    monkeypatch.setattr(drill, "day_attempts", AsyncMock(return_value=[]))
    q = _query("drill:3:2")

    await handle_callback_query(SimpleNamespace(callback_query=q), _ctx(session))  # type: ignore[arg-type]

    args = record.await_args.args
    assert args[1] == date(2026, 11, 22) and args[2] == 3 and args[3] == 2
    assert args[4] == SENT  # sent_at is the question message's own date
    session.commit.assert_awaited_once()
    replies = [c.args[0] for c in q.message.reply_text.await_args_list]
    assert replies[0] == "❌ Not quite. Answer: 4\n2 + 2 = 4"
    assert replies[1].startswith("Aptitude: 0/0")  # the set is finished: the summary


async def test_next_question_has_four_buttons_and_no_key(monkeypatch: pytest.MonkeyPatch):
    session = MagicMock()
    session.commit = AsyncMock()
    outcome = DrillOutcome(
        correct=True, explanation="x", seconds=5.0, chosen="4", answer_option="4"
    )
    monkeypatch.setattr(drill, "record_drill", AsyncMock(return_value=outcome))
    monkeypatch.setattr(drill, "next_unanswered", AsyncMock(return_value=4))
    q = _query("drill:3:0")

    await handle_callback_query(SimpleNamespace(callback_query=q), _ctx(session))  # type: ignore[arg-type]

    last = q.message.reply_text.await_args_list[-1]
    keys = [b.callback_data for row in last.kwargs["reply_markup"].inline_keyboard for b in row]
    assert keys == ["drill:4:0", "drill:4:1", "drill:4:2", "drill:4:3"]
    assert "Answer" not in last.args[0]


async def test_start_drill_sends_the_first_open_question(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(drill, "next_unanswered", AsyncMock(return_value=0))
    update = SimpleNamespace(message=SimpleNamespace(reply_text=AsyncMock()))
    bot_data = {"session_factory": _factory(MagicMock())}
    await drill.start_drill(update, bot_data, "Asia/Kolkata")
    text = update.message.reply_text.await_args.args[0]
    assert text.startswith("Drill 1/20")
