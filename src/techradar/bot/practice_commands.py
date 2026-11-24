"""Phase 3 commands that queue a worker job by name: /quiz and /cards.

The bot only routes the owner's command and defers the job; the job puts the questions or cards
in the outbox (the bot sends outbox rows). Routing has already limited these to authorized chats.

SEC: SEC-26.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from techradar.bot.practice_callbacks import send_next_review
from techradar.worker.names import CARDS, GRAMMAR_SET, QUIZ

COMMAND_JOBS: Mapping[str, str] = {"quiz": QUIZ, "cards": CARDS, "grammar": GRAMMAR_SET}


async def handle_practice_command(update: Any, bot_data: Mapping[str, Any], action: str) -> None:
    """Defer the job of `action`; say so when the job queue is not there."""
    proc_app = bot_data.get("procrastinate_app")
    if proc_app is None:
        await update.message.reply_text("Not available yet.")
        return
    await proc_app.configure_task(name=COMMAND_JOBS[action]).defer_async()


async def handle_inbox(update: Any, bot_data: Mapping[str, Any]) -> None:
    """/inbox: the oldest item waiting for a decision. Routing allows the owner's chat only."""
    session_factory = bot_data.get("session_factory")
    if session_factory is None:
        await update.message.reply_text("Not available yet.")
        return
    await send_next_review(update.message, session_factory)
