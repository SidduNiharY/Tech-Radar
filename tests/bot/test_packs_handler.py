"""Bot wiring for /packs (Phase 2c Task 9): owner-only, read-only starter pack status.

SEC: SEC-05, SEC-26.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from techradar.bot import main as bot_main
from techradar.bot import packs_command
from techradar.library.packs import PackStatus

OWNER = 123


@pytest.fixture(autouse=True)
def _settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    settings = SimpleNamespace(telegram_owner_chat_id=OWNER, data_dir=tmp_path)
    monkeypatch.setattr(bot_main, "get_settings", lambda: settings)


def _update(chat_id: int, text: str):
    update = MagicMock()
    update.effective_chat.id = chat_id
    update.message.text = text
    update.message.reply_to_message = None
    update.message.reply_text = AsyncMock()
    opened: list[object] = []

    @asynccontextmanager
    async def factory():
        opened.append("session")
        yield MagicMock()

    context = MagicMock()
    context.application.bot_data = {"owner_id": OWNER, "session_factory": factory}
    return update, context, opened


async def test_owner_packs_shows_the_status(monkeypatch: pytest.MonkeyPatch) -> None:
    statuses = AsyncMock(
        return_value=[PackStatus(name="gate", exam="gate_cs", approved=False, items=[])]
    )
    monkeypatch.setattr(packs_command, "pack_statuses", statuses)
    update, context, opened = _update(OWNER, "/packs")
    await bot_main.handle_message(update, context)
    update.message.reply_text.assert_awaited_once_with("gate · gate_cs · not approved · 0/0")
    assert opened == ["session"]


async def test_stranger_packs_gets_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    statuses = AsyncMock()
    monkeypatch.setattr(packs_command, "pack_statuses", statuses)
    update, context, opened = _update(999, "/packs")
    await bot_main.handle_message(update, context)
    assert statuses.await_count == 0 and opened == []
    update.message.reply_text.assert_not_called()


async def test_packs_before_the_database_is_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    statuses = AsyncMock()
    monkeypatch.setattr(packs_command, "pack_statuses", statuses)
    update, context, _opened = _update(OWNER, "/packs")
    del context.application.bot_data["session_factory"]
    await bot_main.handle_message(update, context)
    assert statuses.await_count == 0
    update.message.reply_text.assert_awaited_once_with("Not available yet.")
