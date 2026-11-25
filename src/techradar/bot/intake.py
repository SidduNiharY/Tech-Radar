"""Links, PDFs and pasted text from the owner (Phase 3 Task 3).

The bot never writes `data/raw` or `data/parse-jobs` and never fetches a link itself:

- **Link:** the bot defers `owner_link` with the URL; the worker runs `intake_link`
  (`techradar.fetcher.owner`: this module stays importable in the bot image), which
  checks it with `check_url` against the Squid allowlist and inserts a `raw_items` row
  (source 0, status `new`). The fetcher then fetches it through Squid and checks every
  redirect again. The reply comes back through the outbox.
- **PDF:** refused before download unless Telegram says `application/pdf` and at most 5 MB;
  after download the size and the `%PDF-` header are checked again. The bytes are saved as
  `<sha256>.pdf` in the bot's private drop folder (`data/telegram-in`, see
  `techradar.intake.owner_files`) and the worker's `owner_file` job moves them through the
  Intake Gateway and the no-network parser as an owner item.
- **Pasted text:** control characters removed, HTML-escaped, wrapped in a small HTML page and
  saved the same way.

File names from Telegram are never used. Everything here runs only for the owner's own
private chat, sent by the owner (SEC-26); strangers get no reply.

SEC: SEC-05, SEC-06, SEC-17, SEC-25, SEC-26, SEC-57.
"""

from __future__ import annotations

import html
import logging
import re
import unicodedata
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path
from typing import Any

import anyio

from techradar.intake.owner_files import UnsafeFile, write_private
from techradar.worker.names import OWNER_FILE, OWNER_LINK

logger = logging.getLogger(__name__)

MAX_DOC_BYTES = 5_000_000
MIN_PASTE_CHARS = 200
MAX_PASTE_CHARS = 20_000
MAX_LINK_CHARS = 4096  # longer is never a link; check_url refuses over 2000 anyway
PDF_MIME = "application/pdf"

QUEUED_REPLY = "Queued."
DOC_REFUSED_REPLY = "Only PDFs up to 5 MB, please."
NOT_SAVED_REPLY = "Couldn't save that file."
NOT_AVAILABLE_REPLY = "Not available yet."

# A single token with a scheme: `https://…`, and also schemes that are never fetched, so they
# get a clear refusal instead of silence.
_SCHEME_RE = re.compile(r"([A-Za-z][A-Za-z0-9+.\-]{0,20}):\S+")
_NEVER_FETCHED_SCHEMES = frozenset({"javascript", "data", "file", "vbscript"})
_URL_IN_TEXT_RE = re.compile(r"(?i)\b(?:[a-z][a-z0-9+.\-]{0,20}://|www\.)")


def link_in(text: str) -> str | None:
    """The URL if the stripped text is exactly one URL-like token, else None."""
    cleaned = text.strip()
    if not cleaned or len(cleaned) > MAX_LINK_CHARS:
        return None
    m = _SCHEME_RE.fullmatch(cleaned)
    if m is None:
        return None
    if "://" in cleaned or m.group(1).lower() in _NEVER_FETCHED_SCHEMES:
        return cleaned
    return None


def is_paste(text: str) -> bool:
    """Owner text of at least 200 characters with no URL in it."""
    cleaned = text.strip()
    return len(cleaned) >= MIN_PASTE_CHARS and _URL_IN_TEXT_RE.search(cleaned) is None


def _plain(text: str) -> str:
    """No control or format characters (newlines and tabs kept), NFC, capped."""
    text = unicodedata.normalize("NFC", text)
    kept = "".join(
        ch for ch in text if ch in "\n\t" or not unicodedata.category(ch).startswith("C")
    )
    return kept[:MAX_PASTE_CHARS].strip()


def paste_html(text: str) -> bytes:
    """The pasted text as a small HTML page: every paragraph escaped, no markup kept."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", _plain(text)) if p.strip()]
    body = "\n".join(f"<p>{html.escape(p, quote=True)}</p>" for p in paragraphs)
    page = (
        '<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
        "<title>Note from me</title></head>\n"
        f"<body><article>\n{body}\n</article></body></html>\n"
    )
    return page.encode("utf-8")


Defer = Callable[[str], Awaitable[Any]]


async def intake_paste(text: str, in_dir: Path, defer: Defer) -> str:
    """Save the escaped paste in the drop folder and queue it as an owner item."""
    try:
        name = await anyio.to_thread.run_sync(write_private, in_dir, paste_html(text), "html")
    except UnsafeFile, OSError:
        logger.exception("could not save a pasted note")
        return NOT_SAVED_REPLY
    await defer(name)
    return QUEUED_REPLY


def check_document(mime: str | None, size: int | None) -> str | None:
    """Before download: Telegram's declared type and size. None means go ahead."""
    if mime != PDF_MIME or size is None or size <= 0 or size > MAX_DOC_BYTES:
        return DOC_REFUSED_REPLY
    return None


async def intake_document(file_bytes: bytes, mime: str, in_dir: Path, defer: Defer) -> str:
    """After download: the size and the PDF header again, then save and queue."""
    if (
        mime != PDF_MIME
        or len(file_bytes) > MAX_DOC_BYTES
        or b"%PDF-" not in file_bytes[:1024]
        or file_bytes.startswith((b"MZ", b"\x7fELF", b"PK\x03\x04"))
    ):
        return DOC_REFUSED_REPLY
    try:
        name = await anyio.to_thread.run_sync(write_private, in_dir, file_bytes, "pdf")
    except UnsafeFile, OSError:
        logger.exception("could not save a PDF from the owner")
        return NOT_SAVED_REPLY
    await defer(name)
    return QUEUED_REPLY


# --- bot handlers --------------------------------------------------------------------------


def is_owner_message(update: Any, owner_id: int) -> bool:
    """The owner's own chat and sent by the owner (not a forward bot, not a group member)."""
    chat = getattr(update, "effective_chat", None)
    user = getattr(update, "effective_user", None)
    return (
        chat is not None
        and getattr(chat, "id", None) == owner_id
        and user is not None
        and getattr(user, "id", None) == owner_id
    )


def _deferrer(bot_data: Mapping[str, Any], task: str, arg: str) -> Defer | None:
    proc_app = bot_data.get("procrastinate_app")
    if proc_app is None:
        return None

    async def defer(value: str) -> Any:
        return await proc_app.configure_task(name=task).defer_async(**{arg: value})

    return defer


async def handle_link(update: Any, bot_data: Mapping[str, Any], url: str) -> None:
    """Queue the worker's link check; its reply comes through the outbox."""
    defer = _deferrer(bot_data, OWNER_LINK, "url")
    if defer is None:
        await update.message.reply_text(NOT_AVAILABLE_REPLY)
        return
    await defer(url)


async def handle_paste(update: Any, bot_data: Mapping[str, Any], text: str) -> None:
    defer = _deferrer(bot_data, OWNER_FILE, "name")
    in_dir = bot_data.get("owner_in_dir")
    if defer is None or in_dir is None:
        await update.message.reply_text(NOT_AVAILABLE_REPLY)
        return
    await update.message.reply_text(await intake_paste(text, Path(in_dir), defer))


async def handle_document(update: Any, context: Any) -> None:
    """A document from the owner: refused before download unless a PDF of at most 5 MB.

    The caller has already checked `is_owner_message`.
    """
    bot_data = context.application.bot_data
    doc = update.message.document
    refusal = check_document(doc.mime_type, doc.file_size)
    if refusal is not None:
        await update.message.reply_text(refusal)
        return
    defer = _deferrer(bot_data, OWNER_FILE, "name")
    in_dir = bot_data.get("owner_in_dir")
    if defer is None or in_dir is None:
        await update.message.reply_text(NOT_AVAILABLE_REPLY)
        return
    tg_file = await context.bot.get_file(doc.file_id)
    if tg_file.file_size is not None and tg_file.file_size > MAX_DOC_BYTES:
        await update.message.reply_text(DOC_REFUSED_REPLY)
        return
    data = bytes(await tg_file.download_as_bytearray())
    await update.message.reply_text(await intake_document(data, PDF_MIME, Path(in_dir), defer))
