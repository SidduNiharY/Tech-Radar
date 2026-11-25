"""A `voice` outbox message is sent only from the voice folder (Phase 6 Task 6, SEC-15)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from techradar.messaging.outbox import _deliver, voice_file


def _msg(kind: str, file_path: str | None) -> SimpleNamespace:
    return SimpleNamespace(kind=kind, chat_id=42, text="hi", file_path=file_path)


def test_voice_file_accepts_only_real_files_inside_the_folder(tmp_path: Path) -> None:
    out = tmp_path / "out"
    out.mkdir()
    good = out / "reply_1.ogg"
    good.write_bytes(b"x")
    outside = tmp_path / "secret.ogg"
    outside.write_bytes(b"x")
    link = out / "link.ogg"
    link.symlink_to(outside)

    assert voice_file(str(good), out) == good
    assert voice_file(str(outside), out) is None
    assert voice_file(str(link), out) is None
    assert voice_file(str(out / "missing.ogg"), out) is None
    assert voice_file(str(out / ".." / "secret.ogg"), out) is None
    assert voice_file(None, out) is None
    assert voice_file(str(good), None) is None


async def test_voice_message_is_sent_as_voice(tmp_path: Path) -> None:
    out = tmp_path / "out"
    out.mkdir()
    (out / "reply_1.ogg").write_bytes(b"x")
    bot = SimpleNamespace(send_voice=AsyncMock(return_value="sent"), send_message=AsyncMock())
    assert await _deliver(bot, _msg("voice", str(out / "reply_1.ogg")), None, out) == "sent"
    bot.send_voice.assert_awaited_once()
    bot.send_message.assert_not_awaited()


async def test_voice_message_outside_the_folder_is_refused(tmp_path: Path) -> None:
    bot = SimpleNamespace(send_voice=AsyncMock(), send_message=AsyncMock())
    with pytest.raises(ValueError):
        await _deliver(bot, _msg("voice", "/etc/passwd"), None, tmp_path)
    bot.send_voice.assert_not_awaited()


async def test_text_message_is_unchanged() -> None:
    bot = SimpleNamespace(send_message=AsyncMock(return_value="sent"))
    assert await _deliver(bot, _msg("text", None), None, None) == "sent"
    assert bot.send_message.await_args.kwargs["chat_id"] == 42
