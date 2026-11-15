from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import VoiceSession

MAX_VOICE_SECONDS: int = 300
MAX_VOICE_BYTES: int = 10_000_000


def check_voice_limits(
    duration_s: int,
    file_size: int,
    *,
    max_s: int = MAX_VOICE_SECONDS,
    max_bytes: int = MAX_VOICE_BYTES,
) -> str | None:
    """Validate voice duration and byte size limits."""
    if duration_s > max_s:
        return "Please keep voice notes under 5 minutes."
    if file_size > max_bytes:
        return "That file is too large."
    return None


def check_voice_bytes(head: bytes) -> str | None:
    """Validate magic bytes for OGG container."""
    if not head.startswith(b"OggS"):
        return "I can only analyse Telegram voice notes."
    return None


async def intake_voice(
    session: AsyncSession,
    file_bytes: bytes,
    duration_s: int,
    voice_dir: Path,
    defer: Callable[..., Any] | None = None,
) -> int:
    """Store raw voice note with safe permissions and enqueue analysis."""
    in_dir = voice_dir / "in"
    in_dir.mkdir(parents=True, exist_ok=True)
    file_sha = hashlib.sha256(file_bytes).hexdigest()
    out_file = in_dir / f"{file_sha}.ogg"
    out_file.write_bytes(file_bytes)
    out_file.chmod(0o640)

    voice_row = VoiceSession(
        source="telegram",
        duration_s=float(duration_s),
        status="queued",
        audio_path=str(out_file),
    )
    session.add(voice_row)
    await session.flush()

    if defer is not None:
        res = defer("analyse_voice", session_id=voice_row.id)
        if hasattr(res, "__await__"):
            await res

    return int(voice_row.id)
