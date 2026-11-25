"""The bot's voice-note door (Phase 6 Task 1): owner only, checked before download.

SEC: SEC-15, SEC-26, SEC-57.
"""

from __future__ import annotations

import hashlib
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram import Audio, Voice

from techradar.bot import main as bot_main
from techradar.bot.voice_intake import check_voice_metadata
from techradar.voice.intake import GOT_IT_REPLY, NOT_VOICE_REPLY, PRIVACY_NOTICE

OWNER = 42
OGG = b"OggS\x00\x02" + b"v" * 300


def _names(folder: Path) -> list[str]:
    return sorted(p.name for p in folder.iterdir()) if folder.exists() else []


@pytest.fixture(autouse=True)
def _settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    s = SimpleNamespace(telegram_owner_chat_id=OWNER, data_dir=tmp_path, max_question_chars=500)
    monkeypatch.setattr(bot_main, "get_settings", lambda: s)


def _voice(duration: Any = 60, size: int | None = len(OGG), mime: str | None = "audio/ogg"):
    return Voice("fid", "uid", duration, mime_type=mime, file_size=size)


def _update(
    chat_id: int,
    *,
    voice: Voice | None = None,
    audio: Audio | None = None,
    user_id: int | None = None,
    download: bytes = OGG,
    voice_dir: Path | None = None,
    first_notice: bool = True,
):
    update = MagicMock()
    update.effective_chat.id = chat_id
    update.effective_user.id = chat_id if user_id is None else user_id
    update.message.text = None
    update.message.document = None
    update.message.voice = voice
    update.message.audio = audio
    update.message.video_note = None
    update.message.reply_to_message = None
    update.message.reply_text = AsyncMock()
    tg_file = MagicMock()
    tg_file.file_size = len(download)
    tg_file.download_as_bytearray = AsyncMock(return_value=bytearray(download))
    context = MagicMock()
    context.bot.get_file = AsyncMock(return_value=tg_file)

    session = MagicMock()
    added: list[Any] = []
    session.add.side_effect = added.append

    async def flush() -> None:
        for row in added:
            row.id = 17

    session.flush = AsyncMock(side_effect=flush)
    session.commit = AsyncMock()
    notice = MagicMock()
    notice.scalar_one_or_none.return_value = chat_id if first_notice else None
    session.execute = AsyncMock(return_value=notice)
    session.added = added

    @asynccontextmanager
    async def factory():
        yield session

    deferrer = SimpleNamespace(defer_async=AsyncMock())
    proc = MagicMock()
    proc.configure_task = MagicMock(return_value=deferrer)
    context.application.bot_data = {
        "owner_id": OWNER,
        "session_factory": factory,
        "procrastinate_app": proc,
        "voice_dir": voice_dir,
    }
    return update, context, proc, deferrer, session


def _replies(update: MagicMock) -> list[str]:
    return [c.args[0] for c in update.message.reply_text.await_args_list]


async def test_owner_voice_note_is_saved_privately_and_analysis_deferred(tmp_path: Path) -> None:
    voice_dir = tmp_path / "voice"
    update, context, proc, deferrer, session = _update(OWNER, voice=_voice(), voice_dir=voice_dir)
    await bot_main.handle_message(update, context)
    name = hashlib.sha256(OGG).hexdigest() + ".ogg"
    assert _names(voice_dir / "in") == [name]
    assert (voice_dir / "in" / name).stat().st_mode & 0o777 == 0o640
    proc.configure_task.assert_called_once_with(name="analyse_voice", queue="voice")
    deferrer.defer_async.assert_awaited_once_with(session_id=17)
    assert _replies(update) == [GOT_IT_REPLY, PRIVACY_NOTICE]


async def test_privacy_notice_is_sent_once(tmp_path: Path) -> None:
    update, context, _p, _d, _s = _update(
        OWNER, voice=_voice(), voice_dir=tmp_path / "voice", first_notice=False
    )
    await bot_main.handle_message(update, context)
    assert _replies(update) == [GOT_IT_REPLY]


async def test_stranger_voice_note_is_never_downloaded(tmp_path: Path) -> None:
    update, context, proc, _d, _s = _update(7, voice=_voice(), voice_dir=tmp_path / "voice")
    await bot_main.handle_message(update, context)
    context.bot.get_file.assert_not_called()
    update.message.reply_text.assert_not_called()
    proc.configure_task.assert_not_called()


async def test_voice_note_from_another_sender_in_the_owner_chat_is_ignored(
    tmp_path: Path,
) -> None:
    update, context, _p, _d, _s = _update(
        OWNER, voice=_voice(), user_id=999, voice_dir=tmp_path / "voice"
    )
    await bot_main.handle_message(update, context)
    context.bot.get_file.assert_not_called()
    update.message.reply_text.assert_not_called()


@pytest.mark.parametrize(
    ("voice", "reply"),
    [
        (_voice(duration=301), "Please keep voice notes under 5 minutes."),
        (_voice(duration=timedelta(seconds=400)), "Please keep voice notes under 5 minutes."),
        (_voice(size=10_000_001), "That file is too large."),
        (_voice(size=None), "That file is too large."),
        (_voice(mime="video/mp4"), NOT_VOICE_REPLY),
        (_voice(mime="application/x-msdownload"), NOT_VOICE_REPLY),
    ],
)
async def test_voice_note_breaking_a_limit_is_refused_before_download(
    tmp_path: Path, voice: Voice, reply: str
) -> None:
    update, context, proc, _d, _s = _update(OWNER, voice=voice, voice_dir=tmp_path / "voice")
    await bot_main.handle_message(update, context)
    context.bot.get_file.assert_not_called()
    assert _replies(update) == [reply]
    proc.configure_task.assert_not_called()


@pytest.mark.parametrize(
    ("download", "reply"),
    [
        (b"MZ\x90\x00 an exe", NOT_VOICE_REPLY),
        (b"ID3\x04 an mp3", NOT_VOICE_REPLY),
        (b"OggS" + b"x" * 10_000_000, "That file is too large."),
    ],
)
async def test_downloaded_bytes_are_checked_again(
    tmp_path: Path, download: bytes, reply: str
) -> None:
    voice_dir = tmp_path / "voice"
    update, context, proc, _d, session = _update(
        OWNER, voice=_voice(), download=download, voice_dir=voice_dir
    )
    await bot_main.handle_message(update, context)
    assert _replies(update) == [reply]
    assert _names(voice_dir / "in") == [] and session.added == []
    proc.configure_task.assert_not_called()


async def test_symlink_planted_in_the_voice_folder_is_never_followed(tmp_path: Path) -> None:
    voice_dir = tmp_path / "voice"
    (voice_dir / "in").mkdir(parents=True)
    victim = tmp_path / "victim"
    victim.write_text("keep")
    (voice_dir / "in" / (hashlib.sha256(OGG).hexdigest() + ".ogg")).symlink_to(victim)
    update, context, proc, _d, session = _update(OWNER, voice=_voice(), voice_dir=voice_dir)
    await bot_main.handle_message(update, context)
    assert victim.read_text() == "keep"
    assert _replies(update) == ["Couldn't save that file."]
    proc.configure_task.assert_not_called()
    session.commit.assert_not_called()


async def test_owner_audio_file_is_refused_without_download(tmp_path: Path) -> None:
    audio = Audio("fid", "uid", 60, mime_type="audio/mpeg", file_size=1000)
    update, context, _p, _d, _s = _update(OWNER, audio=audio, voice_dir=tmp_path)
    await bot_main.handle_message(update, context)
    context.bot.get_file.assert_not_called()
    assert _replies(update) == [NOT_VOICE_REPLY]


async def test_stranger_audio_file_gets_nothing(tmp_path: Path) -> None:
    audio = Audio("fid", "uid", 60, mime_type="audio/mpeg", file_size=1000)
    update, context, _p, _d, _s = _update(7, audio=audio, voice_dir=tmp_path)
    await bot_main.handle_message(update, context)
    update.message.reply_text.assert_not_called()


def test_check_voice_metadata() -> None:
    assert check_voice_metadata(60, 1000, "audio/ogg") is None
    assert check_voice_metadata(60, 1000, None) is None  # Telegram may omit the type
    assert check_voice_metadata(timedelta(seconds=60), 1000, "audio/ogg") is None
