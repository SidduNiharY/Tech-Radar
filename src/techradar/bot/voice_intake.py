"""The bot side of voice notes (Phase 6 Task 1).

Called from `bot/main.py` only after `is_owner_message` (the owner's own chat, sent by the
owner; SEC-26). Duration, size and type are checked from Telegram's metadata before anything is
downloaded, and the bytes are checked again after. The note is stored by
`techradar.voice.intake.intake_voice`, which defers `analyse_voice` on the `voice` queue.

SEC: SEC-15, SEC-26, SEC-57.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import timedelta
from pathlib import Path
from typing import Any

from techradar.voice.intake import (
    GOT_IT_REPLY,
    MAX_VOICE_BYTES,
    NOT_VOICE_REPLY,
    PRIVACY_NOTICE,
    TOO_LARGE_REPLY,
    VoiceRefused,
    check_voice_bytes,
    check_voice_limits,
    claim_voice_notice,
    intake_voice,
)
from techradar.worker.names import VOICE_QUEUE

logger = logging.getLogger(__name__)

NOT_AVAILABLE_REPLY = "Not available yet."
VOICE_MIMES = frozenset({"audio/ogg", "audio/opus"})


def _seconds(duration: Any) -> int:
    """Telegram gives an int today; newer library versions may give a timedelta."""
    if isinstance(duration, timedelta):
        return int(duration.total_seconds())
    return int(duration)


def check_voice_metadata(duration: Any, file_size: int | None, mime: str | None) -> str | None:
    """Before download. An unknown size is refused: it cannot be checked before download."""
    if mime is not None and mime not in VOICE_MIMES:
        return NOT_VOICE_REPLY
    if file_size is None:
        return TOO_LARGE_REPLY
    return check_voice_limits(_seconds(duration), file_size)


async def handle_voice(update: Any, context: Any) -> None:
    """A voice note from the owner: check, download, store, queue the analysis."""
    bot_data: Mapping[str, Any] = context.application.bot_data
    voice = update.message.voice
    refusal = check_voice_metadata(voice.duration, voice.file_size, voice.mime_type)
    if refusal is not None:
        await update.message.reply_text(refusal)
        return
    session_factory = bot_data.get("session_factory")
    proc_app = bot_data.get("procrastinate_app")
    voice_dir = bot_data.get("voice_dir")
    if session_factory is None or proc_app is None or voice_dir is None:
        await update.message.reply_text(NOT_AVAILABLE_REPLY)
        return

    tg_file = await context.bot.get_file(voice.file_id)
    if tg_file.file_size is not None and tg_file.file_size > MAX_VOICE_BYTES:
        await update.message.reply_text(TOO_LARGE_REPLY)
        return
    data = bytes(await tg_file.download_as_bytearray())
    duration = _seconds(voice.duration)
    refusal = check_voice_limits(duration, len(data)) or check_voice_bytes(data[:4])
    if refusal is not None:
        await update.message.reply_text(refusal)
        return

    async def defer(task: str, **kwargs: Any) -> Any:
        return await proc_app.configure_task(name=task, queue=VOICE_QUEUE).defer_async(**kwargs)

    async with session_factory() as session:
        try:
            await intake_voice(session, data, duration, Path(voice_dir), defer=defer)
        except VoiceRefused as exc:
            await update.message.reply_text(exc.reply)
            return
        first = await claim_voice_notice(session, update.effective_chat.id)
        await session.commit()
    await update.message.reply_text(GOT_IT_REPLY)
    if first:
        await update.message.reply_text(PRIVACY_NOTICE)
