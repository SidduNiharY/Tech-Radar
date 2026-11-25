"""The `keep_voice:<id>` button under a voice report (Phase 6 Task 6).

Only reached after the owner check in `handle_callback_query`; the message must also be in the
owner's own chat (SEC-26).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from techradar.voice.retention import keep_voice


async def handle_keep_voice(query: Any, bot_data: Mapping[str, Any], session_id: int) -> None:
    message = query.message
    if message is None or message.chat.id != bot_data.get("owner_id"):
        await query.answer("Not available.")
        return
    session_factory = bot_data.get("session_factory")
    if session_factory is None:
        await query.answer("Not available yet.")
        return
    async with session_factory() as session:
        kept = await keep_voice(session, session_id)
    await query.answer("Kept." if kept else "That recording is already gone.")
