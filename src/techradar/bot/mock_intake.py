"""Mock-test scorecards sent on Telegram (Phase 8 Task 5).

The owner sends a screenshot (photo, or a PNG/JPEG/PDF file) with the caption `mock`.
Only the owner's own chat is served; anyone else gets no reply at all (SEC-26).

The bot never decodes the image. It checks the size Telegram reports before downloading,
checks it again on the bytes, decides the type from the bytes (never the declared type
or name), refuses an image whose header claims too many pixels, stores the bytes
content-addressed in `raw/` and writes a `purpose="mock"` parse job. The parser sandbox
re-encodes and reads it (no network, 120 s, SEC-06); the worker then extracts the scores
(exams/mock_intake.py) and replies.
"""

from __future__ import annotations

import contextlib
import hashlib
import logging
import os
import re
import uuid
from pathlib import Path
from typing import Any

from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters

from techradar.bot.auth import is_allowed
from techradar.fetcher.store import write_job
from techradar.intake.imagecheck import image_problem
from techradar.schemas.pipeline import ParseJob

logger = logging.getLogger(__name__)

MAX_MOCK_BYTES = 5_000_000
CAPTION = re.compile(r"\s*mock\s*", re.IGNORECASE)
_DOC_TYPES = ("image/png", "image/jpeg", "application/pdf")

QUEUED = "Got it. I'll read the scorecard and reply here."
ONLY_TYPES = "Only PNG or JPEG screenshots (or a PDF) up to 5 MB, please."
TOO_MANY_PIXELS = "That image is too large to read. Please send a normal screenshot."
NOT_AVAILABLE = "Not available yet."

# A photo, or a PNG/JPEG/PDF file, captioned `mock`. Registered before the general
# message handler, so these never reach it; everything else does.
MOCK_FILTER = (
    filters.PHOTO
    | filters.Document.MimeType("image/png")
    | filters.Document.MimeType("image/jpeg")
    | filters.Document.PDF
) & filters.CaptionRegex(r"(?i)^\s*mock\s*$")


def _kind_and_ext(data: bytes) -> tuple[str, str] | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image", "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image", "jpg"
    if data.startswith(b"%PDF-"):
        return "pdf", "pdf"
    return None


def _store(data: bytes, raw_dir: Path, ext: str) -> str:
    """Write `<sha256>.<ext>` into raw/ through a private temp file (never a link)."""
    name = f"{hashlib.sha256(data).hexdigest()}.{ext}"
    raw_dir.mkdir(parents=True, exist_ok=True)
    dfd = os.open(raw_dir, os.O_RDONLY | os.O_DIRECTORY)
    try:
        tmp = f".mock-{uuid.uuid4().hex}.part"
        wfd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o640, dir_fd=dfd)
        try:
            os.write(wfd, data)
            os.fsync(wfd)
        finally:
            os.close(wfd)
        try:
            os.replace(tmp, name, src_dir_fd=dfd, dst_dir_fd=dfd)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(tmp, dir_fd=dfd)
            raise
    finally:
        os.close(dfd)
    return name


def intake_mock_file(data: bytes, raw_dir: Path, jobs_dir: Path) -> str:
    """Queue one scorecard for the parser sandbox; returns the reply for the owner."""
    if len(data) > MAX_MOCK_BYTES:
        return ONLY_TYPES
    found = _kind_and_ext(data)
    if found is None:
        return ONLY_TYPES
    kind, ext = found
    if kind == "image" and image_problem(data) is not None:
        return TOO_MANY_PIXELS
    raw_name = _store(data, raw_dir, ext)
    job = ParseJob(
        job_id=uuid.uuid4().hex,
        kind=kind,  # type: ignore[arg-type]
        raw_name=raw_name,
        url="telegram:mock",
        source_id=0,
        origin="telegram",
        purpose="mock",
    )
    write_job(job, jobs_dir)
    return QUEUED


def _attachment(message: Any) -> tuple[str, int | None] | None:
    """(file id, reported size) of the largest photo or an allowed file."""
    if message.photo:
        best = message.photo[-1]
        return best.file_id, best.file_size
    doc = message.document
    if doc is not None and doc.mime_type in _DOC_TYPES:
        return doc.file_id, doc.file_size
    return None


async def handle_mock_upload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """The owner's captioned scorecard; strangers get no response."""
    message, chat = update.message, update.effective_chat
    if message is None or chat is None:
        return
    bot_data = context.application.bot_data
    owner = bot_data.get("owner_id")
    if owner is None or not is_allowed(chat.id, int(owner)):
        logger.warning("ignored mock upload from chat %s", chat.id)
        return
    if not CAPTION.fullmatch(message.caption or ""):
        return
    found = _attachment(message)
    if found is None:
        await message.reply_text(ONLY_TYPES)
        return
    file_id, size = found
    if size is None or size > MAX_MOCK_BYTES:  # checked before any download
        await message.reply_text(ONLY_TYPES)
        return
    raw_dir, jobs_dir = bot_data.get("raw_dir"), bot_data.get("jobs_dir")
    if raw_dir is None or jobs_dir is None:
        await message.reply_text(NOT_AVAILABLE)
        return
    try:
        tg_file = await context.bot.get_file(file_id)
        data = bytes(await tg_file.download_as_bytearray())
        reply = intake_mock_file(data, Path(raw_dir), Path(jobs_dir))
    except OSError:
        logger.exception("could not queue the mock scorecard")
        reply = NOT_AVAILABLE
    await message.reply_text(reply)


def mock_handler() -> MessageHandler:
    return MessageHandler(MOCK_FILTER, handle_mock_upload)
