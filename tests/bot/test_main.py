"""Bot wiring for /quarantine (Phase 2c): owner-only listing with Release/Delete buttons.

SEC: SEC-14, SEC-26.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram import InlineKeyboardMarkup

from techradar.bot import main as bot_main
from techradar.messaging.outbox import Button

OWNER = 123


@pytest.fixture(autouse=True)
def _settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    settings = SimpleNamespace(telegram_owner_chat_id=OWNER, data_dir=tmp_path)
    monkeypatch.setattr(bot_main, "get_settings", lambda: settings)


def _update(chat_id: int, text: str):
    update = MagicMock()
    update.effective_chat.id = chat_id
    update.message.text = text
    update.message.reply_text = AsyncMock()
    opened: list[object] = []
    session = MagicMock()

    @asynccontextmanager
    async def factory():
        opened.append(session)
        yield session

    context = MagicMock()
    context.application.bot_data = {"owner_id": OWNER, "session_factory": factory}
    return update, context, opened, session


async def test_owner_quarantine_lists_held_files_with_buttons(monkeypatch) -> None:
    listing = AsyncMock(
        return_value=(
            "5. book.pdf · macros · deleted on 21 Nov",
            [[Button(text="Release 5", data="qrel:5"), Button(text="Delete 5", data="qdel:5")]],
        )
    )
    monkeypatch.setattr(bot_main, "quarantine_listing", listing)
    update, context, opened, session = _update(OWNER, "/quarantine")
    await bot_main.handle_message(update, context)
    listing.assert_awaited_once_with(session)
    (text,), kw = update.message.reply_text.call_args
    assert text.startswith("5. book.pdf")
    markup = kw["reply_markup"]
    assert isinstance(markup, InlineKeyboardMarkup)
    assert [[b.callback_data for b in row] for row in markup.inline_keyboard] == [
        ["qrel:5", "qdel:5"]
    ]
    assert [[b.text for b in row] for row in markup.inline_keyboard] == [["Release 5", "Delete 5"]]


async def test_empty_quarantine_has_no_buttons(monkeypatch) -> None:
    monkeypatch.setattr(
        bot_main, "quarantine_listing", AsyncMock(return_value=("Nothing is held for review.", []))
    )
    update, context, _opened, _session = _update(OWNER, "/quarantine")
    await bot_main.handle_message(update, context)
    update.message.reply_text.assert_awaited_once_with(
        "Nothing is held for review.", reply_markup=None
    )


async def test_stranger_quarantine_gets_nothing(monkeypatch) -> None:
    listing = AsyncMock()
    monkeypatch.setattr(bot_main, "quarantine_listing", listing)
    update, context, opened, _session = _update(999, "/quarantine")
    await bot_main.handle_message(update, context)
    assert listing.await_count == 0 and opened == []
    update.message.reply_text.assert_not_called()


async def test_quarantine_before_the_database_is_ready(monkeypatch) -> None:
    listing = AsyncMock()
    monkeypatch.setattr(bot_main, "quarantine_listing", listing)
    update, context, _opened, _session = _update(OWNER, "/quarantine")
    del context.application.bot_data["session_factory"]
    await bot_main.handle_message(update, context)
    assert listing.await_count == 0
    update.message.reply_text.assert_awaited_once_with("Not available yet.")


async def test_post_init_wires_the_quarantine_dependencies(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    factory = object()
    monkeypatch.setattr(bot_main, "make_session_factory", lambda *_a, **_k: factory)
    monkeypatch.setattr(bot_main, "read_secret", MagicMock(side_effect=OSError("no secret")))

    async def idle(*_a, **_k) -> None:
        return None

    monkeypatch.setattr(bot_main, "outbox_worker", idle)
    application = SimpleNamespace(bot=object(), bot_data={})
    settings = SimpleNamespace(
        telegram_owner_chat_id=OWNER, data_dir=tmp_path, db_host="h", db_port=1, db_name="d",
        secrets_dir=tmp_path,
    )  # fmt: skip
    monkeypatch.setattr(bot_main, "get_settings", lambda: settings)
    await bot_main.post_init(application)  # type: ignore[arg-type]
    assert application.bot_data["session_factory"] is factory
    assert application.bot_data["quarantine_dir"] == tmp_path / "quarantine"
    assert application.bot_data["library_dir"] == tmp_path / "library"
    assert application.bot_data["owner_id"] == OWNER
    assert "release_gate" not in application.bot_data  # the bot never gates files itself
