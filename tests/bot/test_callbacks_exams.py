"""Phase 8 callbacks: `srcok:<id>`, `srcno:<id>` (sources) and `drill:<n>:<0-3>` (drills).

SEC: SEC-26. Only the owner, only in the owner's chat.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from techradar.bot import callbacks
from techradar.bot.callbacks import handle_callback_query
from techradar.messaging.outbox import parse_callback

OWNER = 123


def _factory(session: MagicMock) -> MagicMock:
    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=session)
    factory.return_value.__aexit__ = AsyncMock(return_value=False)
    return factory


def _query(data: str, *, user: int = OWNER, chat: int = OWNER, sent: datetime | None = None):
    query = MagicMock()
    query.data = data
    query.from_user.id = user
    query.answer = AsyncMock()
    query.message.chat.id = chat
    query.message.date = sent or datetime(2026, 11, 22, 9, 0, tzinfo=UTC)
    query.message.reply_text = AsyncMock()
    query.edit_message_reply_markup = AsyncMock()
    return query


def _context(session: MagicMock | None = None) -> MagicMock:
    context = MagicMock()
    context.application.bot_data = {
        "owner_id": OWNER,
        "session_factory": _factory(session or MagicMock()),
    }
    return context


def _update(query: MagicMock) -> SimpleNamespace:
    return SimpleNamespace(callback_query=query)


def test_exam_callback_data_is_valid():
    assert parse_callback("srcok:42") == ("srcok", [42])
    assert parse_callback("srcno:42") == ("srcno", [42])
    assert parse_callback("drill:19:3") == ("drill", [19, 3])


@pytest.mark.parametrize("data", ["srcok:7", "srcno:7"])
async def test_stranger_gets_nothing(data: str, monkeypatch: pytest.MonkeyPatch):
    decide = AsyncMock()
    monkeypatch.setattr(callbacks, "decide_source", decide)
    query = _query(data, user=999)

    await handle_callback_query(_update(query), _context())  # type: ignore[arg-type]

    decide.assert_not_called()
    query.answer.assert_awaited_once_with()


@pytest.mark.parametrize(("data", "keep"), [("srcok:7", True), ("srcno:7", False)])
async def test_owner_decides_a_source(data: str, keep: bool, monkeypatch: pytest.MonkeyPatch):
    session = MagicMock()
    session.get = AsyncMock(return_value=SimpleNamespace(id=7, status="suggested"))
    session.commit = AsyncMock()
    decide = AsyncMock()
    monkeypatch.setattr(callbacks, "decide_source", decide)
    query = _query(data)

    await handle_callback_query(_update(query), _context(session))  # type: ignore[arg-type]

    assert decide.await_args.args[1] == 7
    assert decide.await_args.kwargs["keep"] is keep
    session.commit.assert_awaited_once()
    query.answer.assert_awaited_once()


async def test_source_buttons_only_work_in_the_owners_chat(monkeypatch: pytest.MonkeyPatch):
    decide = AsyncMock()
    monkeypatch.setattr(callbacks, "decide_source", decide)
    query = _query("srcok:7", chat=-100555)  # the owner pressed it inside a group

    await handle_callback_query(_update(query), _context())  # type: ignore[arg-type]

    decide.assert_not_called()


async def test_unknown_source_is_a_polite_nothing(monkeypatch: pytest.MonkeyPatch):
    session = MagicMock()
    session.get = AsyncMock(return_value=None)
    decide = AsyncMock()
    monkeypatch.setattr(callbacks, "decide_source", decide)
    query = _query("srcok:7")

    await handle_callback_query(_update(query), _context(session))  # type: ignore[arg-type]

    decide.assert_not_called()
    query.answer.assert_awaited_once()
