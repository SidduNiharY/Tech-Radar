"""`mock` scorecards on Telegram (Phase 8 Task 5).

SEC-26: strangers get no reply and nothing is downloaded. The size is checked before the
download; the type comes from the bytes; an image bomb is refused before it is stored.
"""

from __future__ import annotations

import hashlib
import io
import struct
import zlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from PIL import Image

from techradar.bot import mock_intake as mod
from techradar.bot.mock_intake import (
    MAX_MOCK_BYTES,
    ONLY_TYPES,
    QUEUED,
    TOO_MANY_PIXELS,
    handle_mock_upload,
    intake_mock_file,
)
from techradar.schemas.pipeline import ParseJob

OWNER = 123


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (40, 20), "white").save(buf, format="PNG")
    return buf.getvalue()


def _bomb_png() -> bytes:
    def chunk(kind: bytes, body: bytes) -> bytes:
        return (
            struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))
        )

    ihdr = struct.pack(">IIBBBBB", 100_000, 100_000, 1, 0, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IEND", b"")


def _jobs(jobs: Path) -> list[ParseJob]:
    if not jobs.exists():
        return []
    return [ParseJob.model_validate_json(p.read_text()) for p in jobs.glob("*.job.json")]


def test_png_is_stored_by_hash_and_queued_as_a_mock_image_job(tmp_path: Path):
    data = _png()
    assert intake_mock_file(data, tmp_path / "raw", tmp_path / "jobs") == QUEUED
    [job] = _jobs(tmp_path / "jobs")
    assert (job.kind, job.purpose, job.origin, job.source_id) == ("image", "mock", "telegram", 0)
    assert job.url == "telegram:mock"
    assert job.raw_name == hashlib.sha256(data).hexdigest() + ".png"
    assert (tmp_path / "raw" / job.raw_name).read_bytes() == data


def test_pdf_scorecard_is_a_pdf_job(tmp_path: Path):
    assert intake_mock_file(b"%PDF-1.4\n%%EOF\n", tmp_path / "raw", tmp_path / "jobs") == QUEUED
    [job] = _jobs(tmp_path / "jobs")
    assert job.kind == "pdf" and job.raw_name.endswith(".pdf")


def test_wrong_types_bombs_and_big_files_are_refused_unstored(tmp_path: Path):
    raw, jobs = tmp_path / "raw", tmp_path / "jobs"
    assert intake_mock_file(b"PK\x03\x04" + b"\x00" * 30, raw, jobs) == ONLY_TYPES
    assert intake_mock_file(b"MZ\x90\x00", raw, jobs) == ONLY_TYPES
    assert intake_mock_file(b"<svg onload=alert(1)>", raw, jobs) == ONLY_TYPES
    assert intake_mock_file(_bomb_png(), raw, jobs) == TOO_MANY_PIXELS
    assert intake_mock_file(_png() + b"\x00" * MAX_MOCK_BYTES, raw, jobs) == ONLY_TYPES
    assert _jobs(jobs) == [] and not raw.exists()


def test_planted_link_in_raw_is_replaced_not_followed(tmp_path: Path):
    data = _png()
    raw = tmp_path / "raw"
    raw.mkdir()
    target = tmp_path / "victim.txt"
    target.write_text("keep")
    (raw / (hashlib.sha256(data).hexdigest() + ".png")).symlink_to(target)
    assert intake_mock_file(data, raw, tmp_path / "jobs") == QUEUED
    assert target.read_text() == "keep"
    stored = raw / (hashlib.sha256(data).hexdigest() + ".png")
    assert not stored.is_symlink() and stored.read_bytes() == data


def _update(chat_id: int, *, caption: str = "mock", size: int | None = 1000, photo=True):  # type: ignore[no-untyped-def]
    update = MagicMock()
    update.effective_chat.id = chat_id
    message = update.message
    message.caption = caption
    message.reply_text = AsyncMock()
    if photo:
        message.photo = [
            SimpleNamespace(file_id="small", file_size=10),
            SimpleNamespace(file_id="big", file_size=size),
        ]
        message.document = None
    else:
        message.photo = []
        message.document = SimpleNamespace(file_id="doc", file_size=size, mime_type="image/png")
    return update


def _context(tmp_path: Path, data: bytes):  # type: ignore[no-untyped-def]
    context = MagicMock()
    context.application.bot_data = {
        "owner_id": OWNER,
        "raw_dir": tmp_path / "raw",
        "jobs_dir": tmp_path / "jobs",
    }
    tg_file = MagicMock()
    tg_file.download_as_bytearray = AsyncMock(return_value=bytearray(data))
    context.bot.get_file = AsyncMock(return_value=tg_file)
    return context


async def test_owner_photo_is_downloaded_and_queued(tmp_path: Path):
    update, context = _update(OWNER), _context(tmp_path, _png())
    await handle_mock_upload(update, context)
    context.bot.get_file.assert_awaited_once_with("big")  # the largest size
    update.message.reply_text.assert_awaited_once_with(QUEUED)
    assert len(_jobs(tmp_path / "jobs")) == 1


async def test_stranger_gets_nothing_and_nothing_is_downloaded(tmp_path: Path):
    update, context = _update(999), _context(tmp_path, _png())
    await handle_mock_upload(update, context)
    context.bot.get_file.assert_not_awaited()
    update.message.reply_text.assert_not_awaited()
    assert _jobs(tmp_path / "jobs") == []


async def test_size_is_checked_before_download(tmp_path: Path):
    for size in (MAX_MOCK_BYTES + 1, None):
        update, context = _update(OWNER, size=size), _context(tmp_path, _png())
        await handle_mock_upload(update, context)
        context.bot.get_file.assert_not_awaited()
        update.message.reply_text.assert_awaited_once_with(ONLY_TYPES)


async def test_downloaded_bytes_are_checked_again(tmp_path: Path):
    # Telegram said 1000 bytes; the download is bigger (or not an image at all).
    update = _update(OWNER, photo=False)
    context = _context(tmp_path, b"PK\x03\x04" + b"\x00" * (MAX_MOCK_BYTES + 10))
    await handle_mock_upload(update, context)
    update.message.reply_text.assert_awaited_once_with(ONLY_TYPES)
    assert _jobs(tmp_path / "jobs") == []


async def test_other_captions_are_ignored(tmp_path: Path):
    update, context = _update(OWNER, caption="mock please"), _context(tmp_path, _png())
    await handle_mock_upload(update, context)
    context.bot.get_file.assert_not_awaited()
    update.message.reply_text.assert_not_awaited()


async def test_missing_mounts_say_not_available(tmp_path: Path):
    update, context = _update(OWNER), _context(tmp_path, _png())
    del context.application.bot_data["raw_dir"]
    await handle_mock_upload(update, context)
    update.message.reply_text.assert_awaited_once_with(mod.NOT_AVAILABLE)


def test_filter_matches_captioned_photos_only():
    from telegram import Chat, Message, PhotoSize, Update
    from telegram._utils.datetime import from_timestamp

    def upd(caption: str | None, photo: bool) -> Update:
        msg = Message(
            message_id=1,
            date=from_timestamp(0),
            chat=Chat(id=OWNER, type="private"),
            caption=caption,
            photo=[PhotoSize("f", "u", 10, 10)] if photo else None,
            text=None if photo else "mock",
        )
        return Update(update_id=1, message=msg)

    assert mod.MOCK_FILTER.check_update(upd("mock", True))
    assert mod.MOCK_FILTER.check_update(upd(" MOCK ", True))
    assert not mod.MOCK_FILTER.check_update(upd("not a mock", True))
    assert not mod.MOCK_FILTER.check_update(upd(None, False))  # plain text goes on
