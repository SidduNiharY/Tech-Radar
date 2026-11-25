"""Voice note intake (Phase 6 Task 1).

The bot checks Telegram's metadata (duration, size) before downloading, then the bytes
(`OggS`, size) again; only the owner's own voice notes get here (SEC-26). The note is saved as
`data/voice/in/<sha256>.ogg`, mode 0o640, through `write_private` (no-follow, O_EXCL, never a
name from the user), a `voice_sessions` row is committed, and only then is `analyse_voice`
deferred on the `voice` queue, so the job always finds its row. Every note gets
`delete_after = now + 24 h` at intake, so a note that is never analysed is still deleted; the
analysis sets it again when it finishes.

Before decoding, the analysis runs `voice_file_problem`: a regular file (not a link), within
the size limit, `OggS`, and `ffprobe` (`-protocol_whitelist file`, demuxer `ogg`) must report
an `ogg` container with an audio stream and a duration within the limit (SEC-57).

SEC: SEC-15, SEC-26, SEC-57.
"""

from __future__ import annotations

import inspect
import os
import stat
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import anyio
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import VoiceNotice, VoiceSession
from techradar.intake.media import MediaProbeError, probe_media
from techradar.intake.owner_files import write_private
from techradar.worker.names import ANALYSE_VOICE

MAX_VOICE_SECONDS: int = 300
MAX_VOICE_BYTES: int = 10_000_000
RETENTION = timedelta(hours=24)

TOO_LONG_REPLY = "Please keep voice notes under 5 minutes."
TOO_LARGE_REPLY = "That file is too large."
NOT_VOICE_REPLY = "I can only analyse Telegram voice notes."
GOT_IT_REPLY = "Got it, analysing (about a minute)."
PRIVACY_NOTICE = (
    "Voice notes pass through Telegram's servers. For private practice, use the Voice screen "
    "in the web app (phase 9)."
)


class VoiceRefused(Exception):
    """The note breaks a limit; `reply` is the text for the owner."""

    def __init__(self, reply: str) -> None:
        super().__init__(reply)
        self.reply = reply


def check_voice_limits(
    duration_s: int,
    file_size: int,
    *,
    max_s: int = MAX_VOICE_SECONDS,
    max_bytes: int = MAX_VOICE_BYTES,
) -> str | None:
    """Validate voice duration and byte size limits."""
    if duration_s > max_s:
        return TOO_LONG_REPLY
    if file_size > max_bytes or file_size < 0:
        return TOO_LARGE_REPLY
    return None


def check_voice_bytes(head: bytes) -> str | None:
    """Validate magic bytes for OGG container."""
    if not head.startswith(b"OggS"):
        return NOT_VOICE_REPLY
    return None


async def intake_voice(
    session: AsyncSession,
    file_bytes: bytes,
    duration_s: int,
    voice_dir: Path,
    defer: Callable[..., Any] | None = None,
    *,
    now: datetime | None = None,
) -> int:
    """Save the note privately, commit its row, then defer `analyse_voice`; return the id.

    Raises VoiceRefused if the bytes break a limit (checked again here, whatever the caller
    checked before).
    """
    refusal = check_voice_limits(duration_s, len(file_bytes)) or check_voice_bytes(file_bytes)
    if refusal is not None:
        raise VoiceRefused(refusal)
    in_dir = voice_dir / "in"
    name = await anyio.to_thread.run_sync(write_private, in_dir, file_bytes, "ogg")
    voice_row = VoiceSession(
        source="telegram",
        duration_s=float(duration_s),
        status="queued",
        audio_path=str(in_dir / name),
        delete_after=(now or datetime.now(UTC)) + RETENTION,
    )
    session.add(voice_row)
    await session.flush()
    session_id = int(voice_row.id)
    await session.commit()  # the job must find its row

    if defer is not None:
        res = defer(ANALYSE_VOICE, session_id=session_id)
        if inspect.isawaitable(res):
            await res
    return session_id


async def claim_voice_notice(session: AsyncSession, chat_id: int) -> bool:
    """True the first time only: the privacy notice is sent once per chat."""
    stmt = (
        insert(VoiceNotice)
        .values(chat_id=chat_id)
        .on_conflict_do_nothing(index_elements=["chat_id"])
        .returning(VoiceNotice.chat_id)
    )
    return (await session.execute(stmt)).scalar_one_or_none() is not None


def voice_file_problem(
    path: Path, *, max_s: int = MAX_VOICE_SECONDS, max_bytes: int = MAX_VOICE_BYTES
) -> str | None:
    """None if `path` is a real Ogg voice note within the limits, else the reason."""
    try:
        st = os.lstat(path)
    except OSError:
        return "missing"
    if not stat.S_ISREG(st.st_mode):
        return "not a regular file"
    if st.st_size > max_bytes:
        return "too large"
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as fh:
        if check_voice_bytes(fh.read(4)) is not None:
            return "not ogg"
    try:
        info = probe_media(path, "ogg")
    except MediaProbeError as exc:
        return str(exc)[:120]
    if info.format_name != "ogg" or not info.has_audio or info.has_video:
        return f"container {info.format_name[:40]!r}"
    if info.duration_s > max_s + 1:
        return "too long"
    return None
