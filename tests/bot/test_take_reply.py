"""Bot side of "My take": the reply target, the length check and the queued save (SEC-26)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from techradar.bot import main as bot_main
from techradar.bot.take_reply import TOO_LONG_REPLY, handle_take
from techradar.worker.names import SAVE_TAKE

OWNER = 123


@pytest.fixture(autouse=True)
def _settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    settings = SimpleNamespace(
        telegram_owner_chat_id=OWNER, data_dir=tmp_path, max_question_chars=500
    )
    monkeypatch.setattr(bot_main, "get_settings", lambda: settings)


def _update(chat_id: int, text: str, reply_to: int | None):
    update = MagicMock()
    update.effective_chat.id = chat_id
    update.message.text = text
    update.message.reply_to_message.message_id = reply_to
    if reply_to is None:
        update.message.reply_to_message = None
    update.message.reply_text = AsyncMock()
    session = MagicMock()

    @asynccontextmanager
    async def factory():
        yield session

    deferrer = SimpleNamespace(defer_async=AsyncMock())
    proc = MagicMock()
    proc.configure_task = MagicMock(return_value=deferrer)
    context = MagicMock()
    context.application.bot_data = {
        "owner_id": OWNER,
        "session_factory": factory,
        "procrastinate_app": proc,
    }
    return update, context, proc, deferrer


async def test_reply_to_briefing_queues_save_take(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bot_main, "find_ready_doc", AsyncMock(return_value=None))
    monkeypatch.setattr(bot_main, "find_reply_target", AsyncMock(return_value=("briefing", 3)))
    update, context, proc, deferrer = _update(OWNER, "Rates will fall", reply_to=77)
    await bot_main.handle_message(update, context)
    proc.configure_task.assert_called_once_with(name=SAVE_TAKE)
    deferrer.defer_async.assert_awaited_once_with(briefing_id=3, text="Rates will fall")


async def test_reply_to_other_message_is_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bot_main, "find_ready_doc", AsyncMock(return_value=None))
    monkeypatch.setattr(bot_main, "find_reply_target", AsyncMock(return_value=("answer", 9)))
    update, context, proc, deferrer = _update(OWNER, "Rates will fall", reply_to=77)
    await bot_main.handle_message(update, context)
    deferrer.defer_async.assert_not_awaited()
    update.message.reply_text.assert_not_awaited()


async def test_stranger_is_never_looked_up(monkeypatch: pytest.MonkeyPatch) -> None:
    lookup = AsyncMock(return_value=("briefing", 3))
    monkeypatch.setattr(bot_main, "find_reply_target", lookup)
    update, context, proc, deferrer = _update(999, "Rates will fall", reply_to=77)
    await bot_main.handle_message(update, context)
    lookup.assert_not_awaited()
    deferrer.defer_async.assert_not_awaited()
    update.message.reply_text.assert_not_awaited()


async def test_too_long_take_is_refused_without_queueing() -> None:
    update, context, proc, deferrer = _update(OWNER, "x" * 501, reply_to=77)
    await handle_take(update, context.application.bot_data, "x" * 501, 3)
    update.message.reply_text.assert_awaited_once_with(TOO_LONG_REPLY)
    deferrer.defer_async.assert_not_awaited()


@pytest.mark.db
async def test_reply_target_maps_sent_message_to_purpose_and_ref(session) -> None:
    from datetime import UTC, datetime

    from techradar.bot.reply_target import reply_target_for
    from techradar.db.models import Outbox

    now = datetime.now(UTC)
    session.add(
        Outbox(
            chat_id=OWNER,
            kind="text",
            purpose="briefing",
            text="b",
            ref_id=3,
            sent_at=now,
            sent_message_id=501,
        )
    )
    session.add(Outbox(chat_id=OWNER, kind="text", purpose="briefing", text="unsent", ref_id=4))
    await session.flush()
    assert await reply_target_for(session, OWNER, 501) == ("briefing", 3)
    assert await reply_target_for(session, 999, 501) is None  # another chat
    assert await reply_target_for(session, OWNER, 502) is None
