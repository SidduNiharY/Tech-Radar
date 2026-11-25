"""Voice note intake (Phase 6 Task 1).

The bot checks Telegram's metadata (duration, size) before downloading, then the bytes
(`OggS`, size) again; only the owner's own voice notes get here (SEC-26). The note is saved as
`data/voice/in/<sha256>.ogg`, mode 0o640, through `write_private` (no-follow, O_EXCL, never a
name from the user), a `voice_sessions` row is committed, and only then is `analyse_voice`
deferred on the `voice` queue, so the job always finds its row. Every note gets
`delete_after = now + 24 h` at intake, so a note that is never analysed is still deleted; the
analysis sets it again when it finishes.

The analysis opens the stored note once (`private_voice_copy`): only a hash name directly in
`voice/in`, opened relative to the folder with O_NOFOLLOW, a regular file with one link, within
the size limit, whose bytes still hash to its name. Those bytes go to a private worker-only
temp file (O_EXCL, 0o600), and everything after that (the `voice_file_problem` check, decoding,
transcription) reads that copy only, so the file that was checked is the file that is decoded,
whatever happens to `voice/in` meanwhile. `voice_file_problem`: a regular file (not a link),
within the size limit, `OggS`, and `ffprobe` (`-protocol_whitelist file`, demuxer `ogg`) must
report an `ogg` container with an audio stream and a duration within the limit (SEC-57).

SEC: SEC-15, SEC-26, SEC-57.
"""

from __future__ import annotations

import inspect
import os
import shutil
import stat
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import anyio
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import VoiceNotice, VoiceSession
from techradar.intake.media import MediaProbeError, probe_media
from techradar.intake.owner_files import UnsafeFile, read_private, write_private
from techradar.voice.retention import RETENTION, VOICE_NAME_RE
from techradar.worker.names import ANALYSE_VOICE

MAX_VOICE_SECONDS: int = 300
MAX_VOICE_BYTES: int = 10_000_000

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


COPY_NAME = "note.ogg"
COPY_MODE = 0o600


def private_voice_copy(
    voice_dir: Path,
    audio_path: str,
    *,
    max_bytes: int = MAX_VOICE_BYTES,
    work_root: Path | None = None,
) -> Path:
    """Open the stored note once and copy it to a private temp file; return the copy's path.

    `audio_path` must be `<sha256>.ogg` directly in `voice_dir/in`; `read_private` opens it
    relative to that folder with O_NOFOLLOW, requires a regular file with one link within
    `max_bytes`, and checks the bytes still hash to the name. The copy is created O_EXCL with
    mode 0o600 inside a fresh 0o700 folder (`tempfile.mkdtemp`); remove it with
    `remove_voice_copy`. Raises UnsafeFile for anything else.
    """
    p = Path(audio_path)
    in_dir = voice_dir / "in"
    if p.parent != in_dir or not VOICE_NAME_RE.fullmatch(p.name):
        raise UnsafeFile("not a stored voice note")
    data, _st = read_private(in_dir, p.name, max_bytes)
    work = Path(tempfile.mkdtemp(prefix="voice-", dir=work_root))
    try:
        fd = os.open(
            work / COPY_NAME, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, COPY_MODE
        )
        try:
            view = memoryview(data)
            while view:
                view = view[os.write(fd, view) :]
            os.fchmod(fd, COPY_MODE)  # the umask never changes it
        finally:
            os.close(fd)
    except BaseException:
        shutil.rmtree(work, ignore_errors=True)
        raise
    return work / COPY_NAME


def remove_voice_copy(copy: Path) -> None:
    """Delete a copy made by `private_voice_copy` (its whole private folder)."""
    if copy.name == COPY_NAME and copy.parent.name.startswith("voice-"):
        shutil.rmtree(copy.parent, ignore_errors=True)
