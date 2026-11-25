"""Audio retention: deleted 24 hours after intake or analysis unless the owner taps Keep.

Phase 6 Tasks 1 and 6. Kept free of numpy and the engines, so the bot (the Keep button) and the
worker (the hourly cleanup) can import it.

Deletion is limited to what this code wrote: a hash-named note (`<sha256>.ogg`) directly in
`voice_dir/in`, and our spoken reply `voice_dir/out/reply_<id>.ogg`. Both are removed relative
to a folder opened with O_NOFOLLOW, so a planted link is removed itself, never its target, and a
database path pointing anywhere else is never deleted. A note another session still needs (the
same note sent twice is one file) stays.

SEC: SEC-15, SEC-18.
"""

from __future__ import annotations

import os
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import anyio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import VoiceSession

RETENTION = timedelta(hours=24)
VOICE_NAME_RE = re.compile(r"[0-9a-f]{64}\.ogg")

_DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW


def reply_path(voice_dir: Path, session_id: int) -> Path:
    return voice_dir / "out" / f"reply_{int(session_id)}.ogg"


def _unlink_in(folder: Path, name: str) -> None:
    try:
        dfd = os.open(folder, _DIR_FLAGS)
    except OSError:
        return  # missing, or a link instead of a folder: nothing is deleted
    try:
        os.unlink(name, dir_fd=dfd)  # removes a link itself, never its target
    except FileNotFoundError:
        pass
    finally:
        os.close(dfd)


def _unlink_file(path_str: str, voice_dir: Path) -> None:
    """Remove a stored recording: only a hash-named note directly inside `voice_dir/in`.

    A path from the database is not trusted to point anywhere else.
    """
    p = Path(path_str)
    in_dir = voice_dir / "in"
    if p.parent != in_dir or not VOICE_NAME_RE.fullmatch(p.name):
        return
    _unlink_in(in_dir, p.name)


def _unlink_reply(voice_dir: Path, session_id: int) -> None:
    """Remove the generated spoken reply of a session, if any (never through a link)."""
    _unlink_in(voice_dir / "out", reply_path(voice_dir, session_id).name)


async def keep_voice(session: AsyncSession, session_id: int) -> bool:
    """The Keep recording button: the audio is no longer deleted. False when there is nothing."""
    row = (
        await session.execute(select(VoiceSession).where(VoiceSession.id == session_id))
    ).scalar_one_or_none()
    if row is None or not row.audio_path:
        return False
    row.kept = True
    row.delete_after = None
    await session.commit()
    return True


async def mark_voice_unavailable(
    session: AsyncSession, session_id: int, now: datetime | None = None
) -> bool:
    """No voice engines on this server: the note fails and its audio keeps the 24-hour limit.

    `delete_after` is set if missing and only ever brought closer, never pushed out. The caller
    tells the owner and commits. Returns False if the session does not exist.
    """
    voice_row = await session.get(VoiceSession, session_id)
    if voice_row is None:
        return False
    limit = (now or datetime.now(UTC)) + RETENTION
    voice_row.status = "failed"
    if voice_row.delete_after is None or voice_row.delete_after > limit:
        voice_row.delete_after = limit
    await session.flush()
    return True


async def cleanup_voice(
    session: AsyncSession, now: datetime | None = None, *, voice_dir: Path
) -> int:
    """Delete expired recordings (and our spoken replies) that were not marked 'kept'.

    Every session past `delete_after` and not kept loses its audio file and `audio_path`. The
    file stays if another session still needs it (kept, or not yet expired).
    """
    current_time = now or datetime.now(UTC)
    stmt = (
        select(VoiceSession)
        .where(VoiceSession.kept.is_(False))
        .where(VoiceSession.delete_after.is_not(None))
        .where(VoiceSession.delete_after <= current_time)
        .where(VoiceSession.audio_path.is_not(None))
    )
    expired = (await session.execute(stmt)).scalars().all()
    cleaned = 0
    for s in expired:
        if not s.audio_path:
            continue
        still_needed = (
            await session.execute(
                select(VoiceSession.id)
                .where(VoiceSession.audio_path == s.audio_path)
                .where(VoiceSession.id != s.id)
                .where(
                    VoiceSession.kept.is_(True)
                    | VoiceSession.delete_after.is_(None)
                    | (VoiceSession.delete_after > current_time)
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if still_needed is None:
            await anyio.to_thread.run_sync(_unlink_file, s.audio_path, voice_dir)
        await anyio.to_thread.run_sync(_unlink_reply, voice_dir, s.id)
        s.audio_path = None
        cleaned += 1
    await session.commit()
    return cleaned
