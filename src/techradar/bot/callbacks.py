"""Callback query handlers for Telegram inline keyboards (Phase 2b Task 6).

SEC: SEC-26.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from techradar.library.quarantine import (
    ReleaseRequests,
    confirm_release,
    delete_item,
    request_release,
)
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

    if action in QUARANTINE_ACTIONS:
        if len(args) == 1:
            await _quarantine_callback(query, context.application.bot_data, action, args[0])
        else:
            await query.answer("Invalid request.")
        return

    if action == "save_answer" and len(args) == 1:
        procrastinate_app = context.application.bot_data.get("procrastinate_app")
        if procrastinate_app:
            await procrastinate_app.configure_task(name=SAVE_ANSWER).defer_async(answer_id=args[0])
        await query.answer("Saving to vault...")


QUARANTINE_ACTIONS = frozenset({"qrel", "qrel_ok", "qdel"})

_RELEASE_ANSWERS = {
    "released": "Released. It will be processed as flagged.",
    "rejected": "Still refused: the file failed a check that a release cannot override.",
    "failed": "Could not release it; it stays held.",
    "not_found": "Nothing to release.",
    "expired": "That button expired. Press Release again.",
    "no_request": "Press Release first.",
}
_DELETE_ANSWERS = {
    "deleted": "Deleted.",
    "already": "Already deleted.",
    "refused": "Could not delete that file.",
    "not_found": "Nothing to delete.",
}


async def _quarantine_callback(query: Any, bot_data: Any, action: str, item_id: int) -> None:
    """Release (two steps) or delete a held file. Only reached after the owner check."""
    session_factory = bot_data.get("session_factory")
    if session_factory is None:
        await query.answer("Not available yet.")
        return
    requests = bot_data.get("quarantine_requests")
    if not isinstance(requests, ReleaseRequests):
        requests = bot_data["quarantine_requests"] = ReleaseRequests()
    now = datetime.now(UTC)

    if action == "qrel":
        async with session_factory() as session:
            prompt = await request_release(session, item_id, requests=requests, now=now)
        if prompt is None or query.message is None:
            await query.answer("Nothing to release.")
            return
        text, buttons = prompt
        markup = InlineKeyboardMarkup(
            [[InlineKeyboardButton(b.text, callback_data=b.data) for b in row] for row in buttons]
        )
        await query.message.reply_text(text, reply_markup=markup)
        await query.answer()
        return

    if action == "qrel_ok":
        gate = bot_data.get("release_gate")
        if gate is None:
            await query.answer("Release is not available yet.")
            return
        async with session_factory() as session:
            outcome = await confirm_release(session, item_id, requests=requests, gate=gate, now=now)
            await session.commit()
        logger.info("quarantine release %s: %s", item_id, outcome)
        await query.answer(_RELEASE_ANSWERS.get(outcome, "Done."))
        return

    quarantine_dir = bot_data.get("quarantine_dir")
    if quarantine_dir is None:
        await query.answer("Not available yet.")
        return
    async with session_factory() as session:
        deleted = await delete_item(session, item_id, quarantine_dir=Path(quarantine_dir), now=now)
        await session.commit()
    logger.info("quarantine delete %s: %s", item_id, deleted)
    await query.answer(_DELETE_ANSWERS.get(deleted, "Done."))
