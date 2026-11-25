"""Phase 11 button handlers: feedback taps (`fb_*`).

Reached only from `handle_callback_query` after its owner check. Each handler also needs the
button's message to be in the owner's own chat, so a tap on a message forwarded or shared into a
study group is ignored (SEC-26, SEC-49).

SEC: SEC-26, SEC-48, SEC-49.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from techradar.feedback.signals import parse_feedback_callback, record_feedback

logger = logging.getLogger(__name__)

FEEDBACK_REPLIES = {
    "recorded": "Noted.",
    "duplicate": "Already noted.",
    "rate_limited": "Too many taps for now.",
    "ignored": "Not available.",
}


def owner_message(query: Any, bot_data: Mapping[str, Any]) -> Any | None:
    """The button's message, only when it is in the owner's own chat."""
    message = query.message
    if message is None or message.chat.id != bot_data.get("owner_id"):
        return None
    return message


def is_feedback_action(action: str) -> bool:
    """True for `fb_<signal>` callback actions."""
    return action.startswith("fb_")


async def handle_feedback_callback(
    query: Any, bot_data: Mapping[str, Any], action: str, args: list[int]
) -> None:
    """Record one feedback tap. A bad shape or a foreign chat gets a short answer, no data."""
    session_factory = bot_data.get("session_factory")
    message = owner_message(query, bot_data)
    parsed = parse_feedback_callback(action, args)
    if session_factory is None or message is None or parsed is None:
        await query.answer("Not available.")
        return
    kind, signal, target_id = parsed
    now = datetime.now(UTC)
    async with session_factory() as session:
        result = await record_feedback(
            session,
            kind=kind,
            target_id=target_id,
            signal=signal,
            actor="telegram",
            chat_id=message.chat.id,
            owner_id=int(bot_data["owner_id"]),
            now=now,
        )
        await session.commit()
    await query.answer(FEEDBACK_REPLIES[result])
