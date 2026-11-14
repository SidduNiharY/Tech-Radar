"""Ask one book from the bot: reply to a Ready message, and the chapters list (Phase 2c Task 8).

A Ready message is the outbox row with `purpose="library_ready"`: its `ref_id` is the doc id and
its `sent_message_id` is the Telegram message id the owner replies to, so the reply is mapped to
the book by data that already exists (no new column). Only the owner's chat is ever looked up.

SEC: SEC-26 (owner chat only), SEC-37, SEC-41 (a book question is a normal bounded question).
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import LibraryChapter, LibraryDoc, Outbox
from techradar.security.text import sanitize_text
from techradar.worker.names import ASK

logger = logging.getLogger(__name__)

# The same 12-digit bound as a callback's numbers (messaging.outbox), and a Telegram message id.
MAX_ID = 10**12 - 1
MAX_CHAPTERS_SHOWN = 60
CHAPTER_TITLE_CHARS = 80
BOOK_TITLE_CHARS = 120
LIST_CHARS = 3800  # a Telegram message holds 4,096
READY_PURPOSE = "library_ready"
TOO_LONG = "That question is too long (at most {n} characters)."
USAGE = "Please provide a question, e.g. /ask what is repo rate?"

_SPACE = re.compile(r"\s+")


def valid_id(value: object) -> bool:
    """A real positive int within bounds; a bool, a string or a float never is."""
    return isinstance(value, int) and not isinstance(value, bool) and 0 < value <= MAX_ID


def reply_message_id(message: Any) -> int | None:
    """The id of the message `message` replies to, or None (also for anything not a real id)."""
    replied = getattr(message, "reply_to_message", None)
    value = getattr(replied, "message_id", None)
    return value if valid_id(value) else None


async def ready_doc_for_reply(session: AsyncSession, chat_id: int, message_id: int) -> int | None:
    """The ready book whose Ready message (sent to `chat_id`) has Telegram id `message_id`."""
    if not valid_id(message_id):
        return None
    doc_id = (
        await session.execute(
            select(Outbox.ref_id)
            .join(LibraryDoc, LibraryDoc.id == Outbox.ref_id)
            .where(
                Outbox.chat_id == chat_id,
                Outbox.purpose == READY_PURPOSE,
                Outbox.sent_at.is_not(None),
                Outbox.sent_message_id == message_id,
                LibraryDoc.status == "ready",
            )
            .order_by(Outbox.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return doc_id if valid_id(doc_id) else None


async def find_ready_doc(bot_data: Mapping[str, Any], chat_id: int, message_id: int) -> int | None:
    """Look the reply up with the bot's session factory; None when there is no database."""
    session_factory = bot_data.get("session_factory")
    if session_factory is None:
        return None
    async with session_factory() as session:
        return await ready_doc_for_reply(session, chat_id, message_id)


async def handle_ask(
    update: Any, bot_data: Mapping[str, Any], question: str, *, doc_id: int | None, max_chars: int
) -> None:
    """Defer the `ask` job for a question (of one book when `doc_id` is set) and say so."""
    message = update.message
    if not question:
        await message.reply_text(USAGE)
        return
    if len(question) > max_chars:
        await message.reply_text(TOO_LONG.format(n=max_chars))
        return
    procrastinate_app = bot_data.get("procrastinate_app")
    if procrastinate_app:
        kwargs: dict[str, Any] = {"chat_id": update.effective_chat.id, "question": question}
        if doc_id is not None:
            kwargs["doc_id"] = doc_id
        await procrastinate_app.configure_task(name=ASK).defer_async(**kwargs)
    await message.reply_text("Thinking...")


def _one_line(value: str, limit: int) -> str:
    return _SPACE.sub(" ", sanitize_text(value)).strip()[:limit]


def _span(c: Any) -> str:
    """Pages, or a video's time span, of a chapter; empty when it has neither."""
    if c.page_start is not None:
        if c.page_end is not None and c.page_end != c.page_start:
            return f" (pp. {c.page_start}-{c.page_end})"
        return f" (p. {c.page_start})"
    if c.ts_start is not None:
        return (
            f" ({_clock(c.ts_start)}-{_clock(c.ts_end)})"
            if c.ts_end is not None
            else (f" ({_clock(c.ts_start)})")
        )
    return ""


def _clock(seconds: float) -> str:
    s = max(0, int(seconds))
    return (
        f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"
    )


async def chapters_listing(session: AsyncSession, doc_id: int) -> str | None:
    """The chapters of a ready book (number, title, pages or time span); None if not ready."""
    if not valid_id(doc_id):
        return None
    title = (
        await session.execute(
            select(LibraryDoc.title).where(LibraryDoc.id == doc_id, LibraryDoc.status == "ready")
        )
    ).scalar_one_or_none()
    if title is None:
        return None
    total = (
        await session.execute(
            select(func.count()).select_from(LibraryChapter).where(LibraryChapter.doc_id == doc_id)
        )
    ).scalar_one()
    rows = (
        (
            await session.execute(
                select(LibraryChapter)
                .where(LibraryChapter.doc_id == doc_id)
                .order_by(LibraryChapter.ordinal)
                .limit(MAX_CHAPTERS_SHOWN)
            )
        )
        .scalars()
        .all()
    )
    head = f"{_one_line(title, BOOK_TITLE_CHARS)} · {total} chapters"
    lines = [head]
    used = len(head)
    for n, c in enumerate(rows, 1):
        line = f"{n}. {_one_line(c.title, CHAPTER_TITLE_CHARS)}{_span(c)}"
        if used + len(line) + 1 > LIST_CHARS:
            break
        lines.append(line)
        used += len(line) + 1
    if len(lines) - 1 < total:
        lines.append(f"... and {total - (len(lines) - 1)} more.")
    if total:
        lines.append("Reply to the Ready message with a question to ask this book.")
    return "\n".join(lines)
