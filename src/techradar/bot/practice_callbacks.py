"""Phase 3 button handlers: quiz answers, flashcards and their sources.

Reached only from `handle_callback_query` after its owner check; each handler also needs the
button's message to be in the owner's own chat. Callback data is already validated by
`parse_callback` (`^[a-z_]{1,20}(:[0-9]{1,12}){1,2}$`); the numbers are range-checked here.

SEC: SEC-20, SEC-26.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from techradar.db.models import MCQ, LibraryChapter, LibraryDoc
from techradar.messaging.outbox import Button
from techradar.practice.chapter_cards import render_chapter_list
from techradar.practice.flashcards import rate_card, reveal_card, source_text
from techradar.practice.grammar import answer_grammar
from techradar.practice.quiz import record_answer, render_feedback
from techradar.worker.names import MAKE_CHAPTER_CARDS

logger = logging.getLogger(__name__)

PRACTICE_ACTIONS = frozenset({"ans", "rate", "card_show", "src", "read", "gram"})


def markup(buttons: list[list[Button]]) -> InlineKeyboardMarkup:
    """Telegram inline keyboard from the outbox's button model."""
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(b.text, callback_data=b.data) for b in row] for row in buttons]
    )


def owner_message(query: Any, bot_data: Mapping[str, Any]) -> Any | None:
    """The button's message, only when it is in the owner's own chat."""
    message = query.message
    if message is None or message.chat.id != bot_data.get("owner_id"):
        return None
    return message


def _local_now(bot_data: Mapping[str, Any]) -> datetime:
    tz = bot_data.get("tz")
    return datetime.now(ZoneInfo(str(tz))) if tz else datetime.now(UTC)


async def handle_practice_callback(
    query: Any, bot_data: Mapping[str, Any], action: str, args: list[int]
) -> None:
    """Dispatch one practice button. Anything malformed or unavailable gets a short answer."""
    session_factory = bot_data.get("session_factory")
    message = owner_message(query, bot_data)
    if session_factory is None or message is None:
        await query.answer("Not available yet.")
        return
    if len(args) != (2 if action in ("ans", "rate", "gram") else 1):
        await query.answer("Invalid request.")
        return
    now = _local_now(bot_data)

    if action == "ans":
        await _answer(query, message, session_factory, args[0], args[1], now)
    elif action == "rate":
        await _rate(query, session_factory, args[0], args[1], now)
    elif action == "gram":
        await _grammar(query, message, session_factory, args[0], args[1], now)
    elif action == "read":
        await _read(query, bot_data, args[0])
    elif action == "card_show":
        async with session_factory() as session:
            shown = await reveal_card(session, args[0])
        if shown is None:
            await query.answer("Nothing to show.")
            return
        text, buttons = shown
        await message.reply_text(text, reply_markup=markup(buttons))
        await query.answer()
    else:  # "src"
        async with session_factory() as session:
            text = await source_text(session, args[0])
        if text is None:
            await query.answer("No source for this card.")
            return
        await message.reply_text(text)
        await query.answer()


async def _answer(
    query: Any, message: Any, session_factory: Any, mcq_id: int, chosen: int, now: datetime
) -> None:
    if not 0 <= chosen <= 3:
        await query.answer("Invalid request.")
        return
    try:
        async with session_factory() as session:
            mcq = await session.get(MCQ, mcq_id)
            if mcq is None:
                await query.answer("Nothing to answer.")
                return
            options = list(mcq.options)
            outcome = await record_answer(session, mcq_id, chosen, now)
            await session.commit()
    except IntegrityError:  # two taps at once: the unique (mcq, day) row keeps one attempt
        await query.answer("Already answered.")
        return
    if outcome.already_answered:
        await query.answer("Already answered today.")
        return
    await message.reply_text(render_feedback(outcome, options))
    await query.answer()


async def _rate(query: Any, session_factory: Any, card_id: int, rating: int, now: datetime) -> None:
    if rating not in (1, 2, 3, 4):
        await query.answer("Invalid request.")
        return
    async with session_factory() as session:
        outcome = await rate_card(session, card_id, rating, now)  # type: ignore[arg-type]
        await session.commit()
    await query.answer({"rated": "Saved.", "already_rated": "Already rated."}.get(outcome, "Gone."))


async def _read(query: Any, bot_data: Mapping[str, Any], chapter_id: int) -> None:
    """ "Mark as read" for one chapter: the cards are made by the worker, which then replies."""
    proc_app = bot_data.get("procrastinate_app")
    if proc_app is None:
        await query.answer("Not available yet.")
        return
    await proc_app.configure_task(name=MAKE_CHAPTER_CARDS).defer_async(chapter_id=chapter_id)
    await query.answer("Marking as read...")


async def chapter_buttons(session: Any, doc_id: int) -> tuple[str, list[list[Button]]] | None:
    """The `read:<chapter_id>` buttons of a ready book (what the `chap` button adds)."""
    doc = await session.get(LibraryDoc, doc_id)
    if doc is None:
        return None
    chapters = (
        (
            await session.execute(
                select(LibraryChapter)
                .where(LibraryChapter.doc_id == doc_id)
                .order_by(LibraryChapter.ordinal)
            )
        )
        .scalars()
        .all()
    )
    return render_chapter_list(doc, chapters) if chapters else None


async def _grammar(
    query: Any, message: Any, session_factory: Any, item_id: int, chosen: int, now: datetime
) -> None:
    if not 0 <= chosen <= 3:
        await query.answer("Invalid request.")
        return
    async with session_factory() as session:
        feedback = await answer_grammar(session, item_id, chosen, now)
        await session.commit()
    if feedback is None:
        await query.answer("Nothing to answer.")
        return
    await message.reply_text(feedback)
    await query.answer()
