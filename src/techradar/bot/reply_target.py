"""What a reply points at: the outbox row of the message the owner replied to.

A sent message is the outbox row with `sent_message_id` = its Telegram id, so a reply is mapped
to its `purpose` (for example `briefing`) and `ref_id` (the briefing id) with data that already
exists. Only the owner's chat is looked up.

SEC: SEC-26.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.bot.book_ask import valid_id
from techradar.db.models import Outbox


async def reply_target_for(
    session: AsyncSession, chat_id: int, message_id: int
) -> tuple[str, int | None] | None:
    """`(purpose, ref_id)` of the sent outbox message `message_id` in `chat_id`, or None."""
    if not valid_id(message_id):
        return None
    row = (
        await session.execute(
            select(Outbox.purpose, Outbox.ref_id)
            .where(
                Outbox.chat_id == chat_id,
                Outbox.sent_at.is_not(None),
                Outbox.sent_message_id == message_id,
            )
            .order_by(Outbox.id.desc())
            .limit(1)
        )
    ).first()
    return None if row is None else (row[0], row[1])


async def find_reply_target(
    bot_data: Mapping[str, Any], chat_id: int, message_id: int
) -> tuple[str, int | None] | None:
    """Look the reply up with the bot's session factory; None when there is no database."""
    session_factory = bot_data.get("session_factory")
    if session_factory is None:
        return None
    async with session_factory() as session:
        return await reply_target_for(session, chat_id, message_id)
