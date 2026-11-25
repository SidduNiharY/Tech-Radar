"""`keep_voice:<id>`: owner chat only, and the data matches the callback pattern (SEC-26)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from techradar.bot import voice_callbacks
from techradar.bot.voice_callbacks import handle_keep_voice
from techradar.messaging.outbox import parse_callback

OWNER = 42


def _query(chat_id: int | None) -> MagicMock:
    query = MagicMock()
    query.answer = AsyncMock()
    query.message = None if chat_id is None else SimpleNamespace(chat=SimpleNamespace(id=chat_id))
    return query


def _factory() -> MagicMock:
    session = MagicMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=ctx)


def test_keep_button_data_is_a_valid_callback() -> None:
    assert parse_callback("keep_voice:123") == ("keep_voice", [123])


@pytest.mark.parametrize("chat", [None, 7])
async def test_keep_from_anywhere_but_the_owner_chat_is_refused(chat: int | None) -> None:
    query = _query(chat)
    await handle_keep_voice(query, {"owner_id": OWNER, "session_factory": _factory()}, 1)
    query.answer.assert_awaited_with("Not available.")


async def test_keep_marks_the_recording(monkeypatch: pytest.MonkeyPatch) -> None:
    keep = AsyncMock(return_value=True)
    monkeypatch.setattr(voice_callbacks, "keep_voice", keep)
    query = _query(OWNER)
    await handle_keep_voice(query, {"owner_id": OWNER, "session_factory": _factory()}, 9)
    assert keep.await_args.args[1] == 9
    query.answer.assert_awaited_with("Kept.")

    monkeypatch.setattr(voice_callbacks, "keep_voice", AsyncMock(return_value=False))
    query = _query(OWNER)
    await handle_keep_voice(query, {"owner_id": OWNER, "session_factory": _factory()}, 9)
    query.answer.assert_awaited_with("That recording is already gone.")
