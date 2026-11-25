"""`/setup` (Phase 11 Task 7): three taps per mode become the owner's active style rules.

The router lets `/setup` through from the owner's own chat only; the buttons are checked again
in the callback (owner, and a message in the owner's own chat). A tap picks an option from a
fixed list, so no free text can ever become a rule (SEC-26, SEC-48).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from techradar.messaging.outbox import Button
from techradar.profile.setup import (
    SETUP_MODES,
    SETUP_QUESTIONS,
    apply_setup_choice,
    next_setup_step,
    setup_message,
)


def _markup(buttons: list[list[Button]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(b.text, callback_data=b.data) for b in row] for row in buttons]
    )


async def handle_setup(update: Any, bot_data: Mapping[str, Any]) -> None:
    """Start the setup with the first question of the first mode."""
    text, buttons = setup_message(SETUP_MODES[0], 0)
    await update.message.reply_text(
        "Five minutes, three taps per mode. You can run /setup again any time.\n\n" + text,
        reply_markup=_markup(buttons),
    )


async def handle_setup_callback(
    query: Any, bot_data: Mapping[str, Any], mode: Any, args: list[int]
) -> None:
    """One `set_<mode>:<question>:<option>` tap: store the rule, ask the next question."""
    message = query.message
    session_factory = bot_data.get("session_factory")
    if (
        message is None
        or message.chat.id != bot_data.get("owner_id")
        or session_factory is None
        or len(args) != 2
        or not 0 <= args[0] < len(SETUP_QUESTIONS)
        or not 0 <= args[1] < len(SETUP_QUESTIONS[args[0]]["options"])
    ):
        await query.answer("Not available.")
        return
    async with session_factory() as session:
        await apply_setup_choice(session, mode, args[0], args[1], datetime.now(UTC))
        await session.commit()
    await query.answer("Saved.")
    nxt = next_setup_step(mode, args[0])
    if nxt is None:
        await message.reply_text("Setup done. See and undo rules with /improvements.")
        return
    text, buttons = setup_message(*nxt)
    await message.reply_text(text, reply_markup=_markup(buttons))
