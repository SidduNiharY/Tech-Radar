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
from techradar.bot.drill import answer_drill
from techradar.bot.feedback_callbacks import handle_feedback_callback, is_feedback_action
from techradar.bot.planner_commands import handle_checkin_tap
from techradar.bot.practice_callbacks import (
    PRACTICE_ACTIONS,
    chapter_buttons,
    handle_practice_callback,
    markup,
)
from techradar.bot.predict import handle_outcome_button
from techradar.db.models import TopicSource
from techradar.exams.sources import decide_source
from techradar.feedback.actions import log_action
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

    # --- Phase 11: feedback taps, `fb_<signal>:<kind code>:<id>` ---
    if is_feedback_action(action):
        await handle_feedback_callback(query, context.application.bot_data, action, args)
        return

    if action in PRACTICE_ACTIONS:  # --- Phase 3 ---
        await handle_practice_callback(query, context.application.bot_data, action, args)
        return

    if action == "chap":
        if len(args) == 1 and valid_id(args[0]):
            await _chapters_callback(query, context.application.bot_data, args[0])
        else:
            await query.answer("Invalid request.")
        return

    # --- Phase 5 --- one-tap check-in: sleep:<1-5>, energy:<1-5>, mood:<1-5>
    if action in CHECKIN_ACTIONS:
        message = query.message
        if len(args) != 1 or message is None or message.chat.id != owner_id:
            await query.answer("Invalid request.")
            return
        await query.answer(await handle_checkin_tap(action, args[0], context.application.bot_data))
        return

    # --- Phase 8 ---
    if action in SOURCE_ACTIONS:
        if len(args) == 1:
            await _source_callback(query, context.application.bot_data, action, args[0])
        else:
            await query.answer("Invalid request.")
        return
    if action == "drill":
        if len(args) == 2:
            await answer_drill(query, context.application.bot_data, args[0], args[1])
        else:
            await query.answer("Invalid request.")
        return
    # --- end Phase 8 ---

    # --- Phase 7: prediction outcome buttons, `pred:<id>:<1-3>` ---
    if action == "pred":
        if len(args) == 2 and valid_id(args[0]):
            message = query.message
            if message is None or message.chat.id != owner_id:
                await query.answer("Not available.")
            else:
                await handle_outcome_button(query, context.application.bot_data, args[0], args[1])
        else:
            await query.answer("Invalid request.")
        return

    if action == "save_answer" and len(args) == 1:
        procrastinate_app = context.application.bot_data.get("procrastinate_app")
        factory = context.application.bot_data.get("session_factory")
        if factory is not None:  # --- Phase 11: saving an answer is a `save` action ---
            async with factory() as s:
                await log_action(s, "save", f"answer:{args[0]}", now=datetime.now(UTC))
                await s.commit()
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
    # --- Phase 3: one button per chapter to mark it as read (cards come with it) ---
    async with session_factory() as session:
        shown = await chapter_buttons(session, doc_id)
    if shown is not None:
        read_text, read_buttons = shown
        await message.reply_text(read_text, reply_markup=markup(read_buttons))
    await query.answer()


# tk: confirm a ticket (Phase 4 Task 2b). qrel_ok: the old in-memory second step, gone.
QUARANTINE_ACTIONS = frozenset({"qrel", "qrel_ok", "qdel", "tk"})
CHECKIN_ACTIONS = frozenset({"sleep", "energy", "mood"})  # Phase 5

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
        # Only the held copy: worker-bulk deletes a held doc's original (no library mount here).
        deleted = await delete_item(session, item_id, quarantine_dir=Path(quarantine_dir), now=now)
        await session.commit()
    logger.info("quarantine delete %s: %s", item_id, deleted)
    await query.answer(DELETE_MESSAGES.get(deleted, "Done."))


# --- Phase 8: exams ---------------------------------------------------------------

SOURCE_ACTIONS = frozenset({"srcok", "srcno"})


async def _source_callback(query: Any, bot_data: Any, action: str, source_id: int) -> None:
    """Keep (`srcok`) or dismiss (`srcno`) a suggested topic source (SEC-26).

    Only reached after the owner check, and only for a button in the owner's own chat. A model
    suggestion counts as a source only after this press.
    """
    message = query.message
    if message is None or message.chat.id != bot_data.get("owner_id"):
        await query.answer("Not available.")
        return
    session_factory = bot_data.get("session_factory")
    if session_factory is None:
        await query.answer("Not available yet.")
        return
    keep = action == "srcok"
    async with session_factory() as session:
        source = await session.get(TopicSource, source_id)
        if source is None:
            await query.answer("Nothing to show.")
            return
        await decide_source(session, source_id, keep=keep, now=datetime.now(UTC))
        await session.commit()
    try:
        await query.edit_message_reply_markup(reply_markup=None)  # the buttons are done
    except Exception:  # an old message may not be editable; the decision is saved anyway
        logger.info("could not remove the buttons of source %s", source_id)
    await query.answer("Kept." if keep else "Dismissed.")
