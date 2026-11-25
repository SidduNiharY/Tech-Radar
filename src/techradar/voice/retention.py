"""Audio retention: deleted 24 hours after analysis unless the owner taps Keep (Phase 6 Task 6).

Kept free of numpy and the engines, so the bot and the worker can import it.

SEC: SEC-15.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import anyio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import VoiceSession

RETENTION = timedelta(hours=24)


def reply_path(voice_dir: Path, session_id: int) -> Path:
    return voice_dir / "out" / f"reply_{session_id}.ogg"


def _unlink_file(path_str: str) -> None:
    Path(path_str).unlink(missing_ok=True)


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


async def cleanup_voice(
    session: AsyncSession, now: datetime | None = None, voice_dir: Path | None = None
) -> int:
    """Delete expired recordings (and our spoken replies) that were not marked 'kept'."""
    current_time = now or datetime.now(UTC)
    stmt = (
        select(VoiceSession)
        .where(VoiceSession.kept.is_(False))
        .where(VoiceSession.delete_after.is_not(None))
        .where(VoiceSession.delete_after <= current_time)
    )
    expired = (await session.execute(stmt)).scalars().all()
    cleaned = 0
    for s in expired:
        if voice_dir is not None:
            await anyio.to_thread.run_sync(_unlink_file, str(reply_path(voice_dir, s.id)))
        if s.audio_path:
            await anyio.to_thread.run_sync(_unlink_file, s.audio_path)
            s.audio_path = None
            cleaned += 1
    await session.commit()
    return cleaned
