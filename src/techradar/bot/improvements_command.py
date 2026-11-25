"""`/improvements`: the active rules and the last changes, each with Undo (Phase 11 Task 6).

The router lets this command through from the owner's own chat only (SEC-26).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from techradar.feedback.approval import improvements_listing


async def handle_improvements(update: Any, bot_data: Mapping[str, Any]) -> None:
    """Reply with the rules and changes; `undo:<log id>` buttons restore what a change replaced."""
    session_factory = bot_data.get("session_factory")
    if session_factory is None:
        await update.message.reply_text("Not available yet.")
        return
    async with session_factory() as session:
        text, buttons = await improvements_listing(session)
    markup = (
        InlineKeyboardMarkup(
            [[InlineKeyboardButton(b.text, callback_data=b.data) for b in row] for row in buttons]
        )
        if buttons
        else None
    )
    await update.message.reply_text(text, reply_markup=markup)


async def handle_fix(update: Any, bot_data: Mapping[str, Any], arg: str) -> None:
    """`/fix [<answer id>] <what it should say>`: my own words become a test's must_include.

    The router lets it through from the owner's own chat only. Without an id the latest
    answer is used.
    """
    from datetime import UTC, datetime

    from techradar.feedback.regression import set_must_include

    session_factory = bot_data.get("session_factory")
    if session_factory is None:
        await update.message.reply_text("Not available yet.")
        return
    first, _, rest = arg.strip().partition(" ")
    if first.isdigit() and len(first) <= 12 and rest.strip():
        answer_id, text = int(first), rest
    else:
        answer_id, text = None, arg
    async with session_factory() as session:
        reply = await set_must_include(session, text, answer_id, now=datetime.now(UTC))
        await session.commit()
    await update.message.reply_text(reply)
