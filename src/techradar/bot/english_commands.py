"""The bot side of English practice (Phase 6 Tasks 7, 8): /polish, essay and reflection replies,
and the /story questions.

The router lets these through from the owner's own chat only (SEC-26). The bot never calls a
model: it checks the length and queues a job by name; `/story` is plain database work.

SEC: SEC-15, SEC-17, SEC-26.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from techradar.english.stories import open_draft, story_step
from techradar.english.writing import route_and_validate_polish
from techradar.worker.names import ESSAY_REPLY, POLISH, REFLECTION_SAVE

logger = logging.getLogger(__name__)

NOT_AVAILABLE = "Not available yet."
MAX_ESSAY_CHARS = 4000
USAGE_POLISH = "Send /polish followed by your text."


async def _defer(bot_data: Mapping[str, Any], name: str, **kwargs: Any) -> bool:
    proc_app = bot_data.get("procrastinate_app")
    if proc_app is None:
        return False
    await proc_app.configure_task(name=name).defer_async(**kwargs)
    return True


async def handle_polish(update: Any, bot_data: Mapping[str, Any], text: str) -> None:
    if not text.strip():
        await update.message.reply_text(USAGE_POLISH)
        return
    refusal = route_and_validate_polish(text)
    if refusal is not None:
        await update.message.reply_text(refusal)
        return
    if not await _defer(bot_data, POLISH, text=text):
        await update.message.reply_text(NOT_AVAILABLE)


async def handle_essay_reply(
    update: Any, bot_data: Mapping[str, Any], ref_id: int, text: str
) -> None:
    """A reply to the weekly essay or letter prompt; a reply within 30 minutes is timed."""
    if len(text) > MAX_ESSAY_CHARS:
        await update.message.reply_text(f"Keep it under {MAX_ESSAY_CHARS:,} characters.")
        return
    prompt = update.message.reply_to_message
    timed = prompt is not None and (update.message.date - prompt.date).total_seconds() <= 30 * 60
    if not await _defer(bot_data, ESSAY_REPLY, ref_id=ref_id, text=text, timed=timed):
        await update.message.reply_text(NOT_AVAILABLE)


async def handle_reflection_reply(update: Any, bot_data: Mapping[str, Any], text: str) -> None:
    if len(text) > MAX_ESSAY_CHARS:
        await update.message.reply_text(f"Keep it under {MAX_ESSAY_CHARS:,} characters.")
        return
    if await _defer(bot_data, REFLECTION_SAVE, text=text):
        await update.message.reply_text("Saved your reflection.")
    else:
        await update.message.reply_text(NOT_AVAILABLE)


async def story_is_open(bot_data: Mapping[str, Any], chat_id: int) -> bool:
    """Does this chat have an unfinished /story draft? False when there is no database."""
    session_factory = bot_data.get("session_factory")
    if session_factory is None:
        return False
    async with session_factory() as session:
        return await open_draft(session, chat_id) is not None


async def handle_story(
    update: Any, bot_data: Mapping[str, Any], chat_id: int, text: str | None
) -> None:
    """`/story` (text None) starts a story; a plain reply fills the next question."""
    session_factory = bot_data.get("session_factory")
    if session_factory is None:
        await update.message.reply_text(NOT_AVAILABLE)
        return
    vault_root = bot_data.get("vault_root")
    async with session_factory() as session:
        reply = await story_step(
            session, chat_id, text, Path(vault_root) if vault_root is not None else None
        )
    await update.message.reply_text(reply)
