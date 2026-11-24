"""Bot side of the predictions log (Phase 7 Task 6): /predict, the outcome buttons, replies.

Owner only (SEC-26): the router sends `/predict` and prediction replies here from the owner's own
chat only, and the button handler runs after the owner check. The bot has no vault, so every
change defers `predictions_sync_job` and the worker regenerates `context/predictions.md`.

SEC: SEC-26.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.bot.book_ask import valid_id
from techradar.db.models import Outbox
from techradar.worker.names import PREDICTIONS_SYNC
from techradar.world.predictions import (
    OUTCOMES,
    PREDICTION_PURPOSE,
    parse_predict,
    record_outcome,
    record_prediction,
    set_outcome_text,
)

logger = logging.getLogger(__name__)

NOT_AVAILABLE = "Not available yet."
NOTED = "Noted."


async def prediction_for_reply(session: AsyncSession, chat_id: int, message_id: int) -> int | None:
    """The prediction whose reminder (sent to `chat_id`) has Telegram message id `message_id`."""
    if not valid_id(message_id):
        return None
    ref = (
        await session.execute(
            select(Outbox.ref_id)
            .where(
                Outbox.chat_id == chat_id,
                Outbox.purpose == PREDICTION_PURPOSE,
                Outbox.sent_at.is_not(None),
                Outbox.sent_message_id == message_id,
            )
            .order_by(Outbox.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return ref if valid_id(ref) else None


async def find_prediction(bot_data: Mapping[str, Any], chat_id: int, message_id: int) -> int | None:
    """Look a reply up with the bot's session factory; None when there is no database."""
    session_factory = bot_data.get("session_factory")
    if session_factory is None:
        return None
    async with session_factory() as session:
        return await prediction_for_reply(session, chat_id, message_id)


async def _sync_vault(bot_data: Mapping[str, Any]) -> None:
    procrastinate_app = bot_data.get("procrastinate_app")
    if procrastinate_app is None:
        return
    try:
        await procrastinate_app.configure_task(name=PREDICTIONS_SYNC).defer_async()
    except Exception:  # the database is already right; the daily job regenerates the page
        logger.warning("could not queue the predictions page update", exc_info=True)


async def handle_predict(
    update: Any, bot_data: Mapping[str, Any], arg: str, *, today: date
) -> None:
    """`/predict <text> by YYYY-MM-DD`: validate, save, confirm."""
    message = update.message
    parsed = parse_predict(arg, today)
    if isinstance(parsed, str):
        await message.reply_text(parsed)
        return
    session_factory = bot_data.get("session_factory")
    if session_factory is None:
        await message.reply_text(NOT_AVAILABLE)
        return
    text, due = parsed
    async with session_factory() as session:
        await record_prediction(session, text, due)
        await session.commit()
    await _sync_vault(bot_data)
    await message.reply_text(f"Saved. I'll ask you on {due.day} {due:%b %Y}.")


async def handle_prediction_reply(
    update: Any, bot_data: Mapping[str, Any], prediction_id: int, text: str
) -> None:
    """The owner's reply to a reminder: keep the words with the prediction."""
    message = update.message
    session_factory = bot_data.get("session_factory")
    if session_factory is None:
        await message.reply_text(NOT_AVAILABLE)
        return
    async with session_factory() as session:
        saved = await set_outcome_text(session, prediction_id, text)
        await session.commit()
    if saved:
        await _sync_vault(bot_data)
    await message.reply_text(NOTED if saved else "Nothing to save.")


async def handle_outcome_button(
    query: Any, bot_data: Mapping[str, Any], prediction_id: int, outcome: int
) -> None:
    """`pred:<id>:<1-3>`: only reached after the owner check in the callback handler."""
    if not valid_id(prediction_id) or outcome not in OUTCOMES:
        await query.answer("Invalid request.")
        return
    session_factory = bot_data.get("session_factory")
    if session_factory is None:
        await query.answer(NOT_AVAILABLE)
        return
    async with session_factory() as session:
        saved = await record_outcome(session, prediction_id, outcome)
        await session.commit()
    if saved:
        await _sync_vault(bot_data)
    await query.answer(
        f"{OUTCOMES[outcome]}. Reply to the message to say what happened."
        if saved
        else "Already answered."
    )
