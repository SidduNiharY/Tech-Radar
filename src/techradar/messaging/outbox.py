"""Outbox queue management and delivery for Telegram messaging (Phase 2b Task 6).

SEC: SEC-26, SEC-37, SEC-39, SEC-41.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, LinkPreviewOptions

from techradar.db.models import Outbox

logger = logging.getLogger(__name__)

_CALLBACK_PATTERN = re.compile(r"^[a-z_]{1,20}(:[0-9]{1,12}){1,2}$")


class Button(BaseModel):
    """Inline keyboard button specification for outbound messages."""

    text: Annotated[str, Field(min_length=1, max_length=32)]
    data: Annotated[str, Field(pattern=r"^[a-z_]{1,20}(:[0-9]{1,12}){1,2}$")]


def parse_callback(data: str) -> tuple[str, list[int]] | None:
    """Parse and validate callback query data into an action and integer arguments."""
    if not isinstance(data, str) or len(data) > 64:
        return None
    if not _CALLBACK_PATTERN.match(data):
        return None
    parts = data.split(":")
    action = parts[0]
    try:
        args = [int(p) for p in parts[1:]]
        return (action, args)
    except ValueError:
        return None


async def enqueue_message(
    session: AsyncSession,
    chat_id: int,
    text: str,
    *,
    purpose: str,
    buttons: list[list[Button]] | None = None,
    kind: Literal["text", "voice", "document"] = "text",
    file_path: str | None = None,
    ref_id: int | None = None,
) -> int:
    """Enqueue an outbound message for delivery via Telegram outbox."""
    truncated = text[:4096]
    buttons_data = (
        [[b.model_dump() for b in row] for row in buttons] if buttons is not None else None
    )

    msg = Outbox(
        chat_id=chat_id,
        text=truncated,
        purpose=purpose,
        buttons=buttons_data,
        kind=kind,
        file_path=file_path,
        ref_id=ref_id,
        attempts=0,
    )
    session.add(msg)
    await session.flush()
    return msg.id


async def send_pending(
    bot: Any,
    session_factory: async_sessionmaker[AsyncSession],
    *,
    limit: int = 20,
) -> int:
    """Send up to limit pending outbox messages via Telegram."""
    sent_count = 0
    async with session_factory() as session:
        stmt = (
            select(Outbox)
            .where(Outbox.sent_at.is_(None), Outbox.attempts < 5)
            .order_by(Outbox.id.asc())
            .limit(limit)
        )
        res = await session.execute(stmt)
        messages = list(res.scalars().all())

        for msg in messages:
            try:
                reply_markup = None
                if msg.buttons:
                    keyboard = [
                        [InlineKeyboardButton(b["text"], callback_data=b["data"]) for b in row]
                        for row in msg.buttons
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)

                link_opts = LinkPreviewOptions(is_disabled=True)
                sent = await bot.send_message(
                    chat_id=msg.chat_id,
                    text=msg.text,
                    reply_markup=reply_markup,
                    link_preview_options=link_opts,
                )
                msg.sent_at = datetime.now(UTC)
                msg.sent_message_id = getattr(sent, "message_id", 1)
                sent_count += 1
            except Exception as exc:
                msg.attempts += 1
                msg.last_error = str(exc)[:500]
                logger.warning(
                    "Failed to deliver outbox message %d (attempt %d): %s",
                    msg.id,
                    msg.attempts,
                    exc,
                )

        await session.commit()

    return sent_count
