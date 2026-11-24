"""Telegram daily drills: `/drill` and the buttons `drill:<n>:<0-3>` (Phase 8 Task 4).

Every key is computed in code (`exams.drills`); no model is involved. Nothing is kept in
memory: the day comes from the question message's own date, the time taken from the same date,
and what is answered from `drill_attempts`.

SEC: SEC-26 (owner chat only; the router and the callback handler check the owner first).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from techradar.exams.deliver import (
    DRILL_SIZE,
    day_attempts,
    drill_day,
    next_unanswered,
    record_drill,
    render_drill_feedback,
    render_drill_item,
    render_drill_summary,
)
from techradar.exams.drills import daily_set

logger = logging.getLogger(__name__)


def _markup(buttons: list[list[Any]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(b.text, callback_data=b.data) for b in row] for row in buttons]
    )


async def _send_next(message: Any, session: Any, day: Any) -> None:
    """Send the next unanswered question of the day, or the day's summary."""
    n = await next_unanswered(session, day)
    if n is None:
        await message.reply_text(render_drill_summary(await day_attempts(session, day)))
        return
    text, buttons = render_drill_item(daily_set(day)[n], n)
    await message.reply_text(text, reply_markup=_markup(buttons))


async def start_drill(update: Any, bot_data: Any, tz: str) -> None:
    """`/drill`: the first question of today's set that is still open."""
    session_factory = bot_data.get("session_factory")
    if session_factory is None:
        await update.message.reply_text("Not available yet.")
        return
    day = drill_day(datetime.now(UTC), tz)
    async with session_factory() as session:
        await _send_next(update.message, session, day)


async def answer_drill(query: Any, bot_data: Any, n: int, choice: int) -> None:
    """A tap on `drill:<n>:<choice>`: record it, show the result, send the next question."""
    message = query.message
    if message is None or message.chat.id != bot_data.get("owner_id"):
        await query.answer("Not available.")
        return
    session_factory = bot_data.get("session_factory")
    if session_factory is None:
        await query.answer("Not available yet.")
        return
    if not (0 <= n < DRILL_SIZE and 0 <= choice <= 3):
        await query.answer("Invalid request.")
        return
    sent_at = message.date
    day = drill_day(sent_at, bot_data.get("tz") or "UTC")
    async with session_factory() as session:
        try:
            outcome = await record_drill(session, day, n, choice, sent_at, datetime.now(UTC))
        except ValueError:
            await query.answer("Invalid request.")
            return
        await session.commit()
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:  # an old message may not be editable; the answer is saved anyway
            logger.info("could not remove the drill buttons")
        await message.reply_text(render_drill_feedback(outcome))
        if not outcome.already_answered:
            await _send_next(message, session, day)
    await query.answer()
