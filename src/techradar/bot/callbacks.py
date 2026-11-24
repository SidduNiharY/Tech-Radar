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

from techradar.bot.book_ask import chapters_listing, valid_id
from techradar.library.quarantine import DELETE_MESSAGES, delete_item, release_prompt
from techradar.messaging.outbox import parse_callback
from techradar.tickets import create_ticket, run_confirmed, tg_session_id, token_for
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

    if action == "chap":
        if len(args) == 1 and valid_id(args[0]):
            await _chapters_callback(query, context.application.bot_data, args[0])
        else:
            await query.answer("Invalid request.")
        return

    if action == "save_answer" and len(args) == 1:
        procrastinate_app = context.application.bot_data.get("procrastinate_app")
        if procrastinate_app:
            await procrastinate_app.configure_task(name=SAVE_ANSWER).defer_async(answer_id=args[0])
        await query.answer("Saving to vault...")


async def _chapters_callback(query: Any, bot_data: Any, doc_id: int) -> None:
    """List a ready book's chapters. Only after the owner check, and only in the owner's chat."""
    message = query.message
    if message is None or message.chat.id != bot_data.get("owner_id"):
        await query.answer("Not available.")
        return
    session_factory = bot_data.get("session_factory")
    if session_factory is None:
        await query.answer("Not available yet.")
        return
    async with session_factory() as session:
        text = await chapters_listing(session, doc_id)
    if text is None:
        await query.answer("Nothing to show.")
        return
    await message.reply_text(text)
    await query.answer()


# tk: confirm a ticket (Phase 4 Task 2b). qrel_ok: the old in-memory second step, gone.
QUARANTINE_ACTIONS = frozenset({"qrel", "qrel_ok", "qdel", "tk"})

EXPIRED_ANSWER = "That confirmation expired. Try again."
INVALID_ANSWER = "That confirmation is no longer valid."


async def _quarantine_callback(query: Any, bot_data: Any, action: str, item_id: int) -> None:
    """Release (through a ticket) or delete a held file. Only reached after the owner check.

    `qrel:<id>` stores a ticket for this chat (`tg:<chat_id>`, 60 s) and shows `tk:<ticket>`;
    `tk:<ticket>` runs that ticket's stored action once (techradar.tickets).
    """
    if action == "qrel_ok":
        await query.answer("That button expired. Press Release again.")
        return
    session_factory = bot_data.get("session_factory")
    message = query.message
    if session_factory is None or message is None:
        await query.answer("Not available yet.")
        return
    session_id = tg_session_id(message.chat.id)
    now = datetime.now(UTC)

    if action == "qrel":
        async with session_factory() as session:
            text = await release_prompt(session, item_id)
            if text is None:
                await query.answer("Nothing to release.")
                return
            ticket = await create_ticket(
                session,
                session_id=session_id,
                channel="telegram",
                action="quarantine.release",
                args={"id": item_id},
                summary=text,
                now=now,
            )
            await session.commit()
        markup = InlineKeyboardMarkup(
            [[InlineKeyboardButton("Yes, release", callback_data=f"tk:{ticket.id}")]]
        )
        await message.reply_text(text, reply_markup=markup)
        await query.answer()
        return

    if action == "tk":
        async with session_factory() as session:
            token = await token_for(session, item_id, session_id)
            if token is None:
                await query.answer(INVALID_ANSWER)
                return
            result, reply = await run_confirmed(session, token, session_id, now)
            await session.commit()
        logger.info("ticket %s: %s", item_id, result)
        if result == "ok":
            await query.answer(reply or "Done.")
        elif result == "expired":
            await query.answer(EXPIRED_ANSWER)
        else:
            await query.answer(INVALID_ANSWER)
        return

    quarantine_dir = bot_data.get("quarantine_dir")
    if quarantine_dir is None:
        await query.answer("Not available yet.")
        return
    async with session_factory() as session:
        library_dir = bot_data.get("library_dir")
        deleted = await delete_item(
            session,
            item_id,
            quarantine_dir=Path(quarantine_dir),
            now=now,
            library_dir=Path(library_dir) if library_dir is not None else None,
        )
        await session.commit()
    logger.info("quarantine delete %s: %s", item_id, deleted)
    await query.answer(DELETE_MESSAGES.get(deleted, "Done."))
