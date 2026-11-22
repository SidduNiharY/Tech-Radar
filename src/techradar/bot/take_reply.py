"""The bot side of "My take" (Phase 3 Task 2): check the length, queue the save by name.

The bot never writes the vault or the takes table itself; the worker's `save_take` job does and
sends the confirmation through the outbox.

SEC: SEC-17, SEC-24, SEC-26.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from techradar.briefing.takes import MAX_TAKE_CHARS
from techradar.worker.names import SAVE_TAKE

TOO_LONG_REPLY = f"Keep it under {MAX_TAKE_CHARS} characters."
NOT_AVAILABLE_REPLY = "Not available yet."


async def handle_take(
    update: Any, bot_data: Mapping[str, Any], text: str, briefing_id: int
) -> None:
    """Queue the save of one take; answer at once only when it cannot be queued."""
    if len(text) > MAX_TAKE_CHARS:
        await update.message.reply_text(TOO_LONG_REPLY)
        return
    proc_app = bot_data.get("procrastinate_app")
    if proc_app is None:
        await update.message.reply_text(NOT_AVAILABLE_REPLY)
        return
    await proc_app.configure_task(name=SAVE_TAKE).defer_async(briefing_id=briefing_id, text=text)
