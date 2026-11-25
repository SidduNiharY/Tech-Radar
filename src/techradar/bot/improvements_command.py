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
