"""Callback query handlers for Telegram inline keyboards (Phase 2b Task 6).

SEC: SEC-26.
"""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from techradar.messaging.outbox import parse_callback
from techradar.worker.names import SAVE_ANSWER

logger = logging.getLogger(__name__)


async def handle_callback_query(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Handle incoming callback queries from inline keyboard button presses."""
    query = update.callback_query
    if not query or not query.data:
        return

    parsed = parse_callback(query.data)
    if not parsed:
        await query.answer("Invalid request.")
        return

    action, args = parsed
    owner_id = context.application.bot_data.get("owner_id")
    if query.from_user.id != owner_id:
        logger.warning("Ignored callback query from non-owner %s", query.from_user.id)
        await query.answer()
        return

    if action == "save_answer" and len(args) == 1:
        procrastinate_app = context.application.bot_data.get("procrastinate_app")
        if procrastinate_app:
            await procrastinate_app.configure_task(name=SAVE_ANSWER).defer_async(answer_id=args[0])
        await query.answer("Saving to vault...")
