"""Media checks for video and audio (Intake Gateway step 4, Phase 2c, SEC-44).

ffprobe runs inside the no-network parser, with the container type forced
from the file's own signature (`-f`), a container allowlist
(`-format_whitelist`) and only the `file` protocol. A playlist or concat list
can therefore never make it open another file.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from pydantic import BaseModel

from techradar.schemas.pipeline import IntakeStep

# ffprobe's names for the allowed containers (format_name in its output).
ALLOWED_CONTAINERS = frozenset({"mov,mp4,m4a,3gp,3g2,mj2", "matroska,webm", "mp3", "wav", "ogg"})
# Demuxer short names passed to -format_whitelist.
DEMUXER_WHITELIST = "mov,matroska,mp3,wav,ogg"
_DEMUXER_FOR_MIME = {
    "video/mp4": "mov",
    "video/quicktime": "mov",
    "audio/mp4": "mov",
    "audio/x-m4a": "mov",
    "video/webm": "matroska",
    "video/x-matroska": "matroska",
    "audio/mpeg": "mp3",
    "audio/wav": "wav",
    "audio/ogg": "ogg",
}
# Text that must never appear at the start of a media file.
PLAYLIST_MARKERS = (b"#EXTM3U", b"ffconcat", b"#EXT-X-")


class MediaProbeError(RuntimeError):
    """ffprobe could not read the file as the expected container."""


class MediaInfo(BaseModel):
    format_name: str
    duration_s: float
    has_audio: bool
    has_video: bool


def demuxer_for(mime: str) -> str | None:
    """The ffmpeg demuxer for a detected media type, or None if not media."""
    return _DEMUXER_FOR_MIME.get(mime)


def probe_media(path: Path, demuxer: str, timeout_s: int = 30) -> MediaInfo:
    """Run ffprobe (list args, no shell) and read the container and streams."""
    args = [
        "ffprobe",
        "-v",
        "error",
        "-protocol_whitelist",
        "file",
        "-format_whitelist",
        DEMUXER_WHITELIST,
        "-f",
        demuxer,
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    try:
        res = subprocess.run(  # noqa: S603
            args, capture_output=True, text=True, timeout=timeout_s, check=False
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
        raise MediaProbeError(f"ffprobe failed: {type(exc).__name__}") from exc
    if res.returncode != 0:
        raise MediaProbeError(f"ffprobe refused the file: {(res.stderr or '').strip()[:200]}")
    try:
        data = json.loads(res.stdout or "{}")
        fmt = data.get("format") or {}
        streams = data.get("streams") or []
        types = {str(s.get("codec_type")) for s in streams}
        return MediaInfo(
            format_name=str(fmt.get("format_name", "")),
            duration_s=float(fmt.get("duration") or 0.0),
            has_audio="audio" in types,
            has_video="video" in types,
        )
    except (ValueError, TypeError, AttributeError) as exc:
        raise MediaProbeError(f"unreadable ffprobe output: {type(exc).__name__}") from exc


def check_media(info: MediaInfo, max_s: int, kind: str) -> IntakeStep:
    """Reject other containers, unknown or over-long durations, wrong streams."""
    if info.format_name not in ALLOWED_CONTAINERS:
        return IntakeStep(
            name="structure", outcome="reject", detail=f"container {info.format_name[:60]!r}"
        )
    if info.duration_s <= 0:
        return IntakeStep(name="structure", outcome="reject", detail="unknown duration")
    if info.duration_s > max_s:
        return IntakeStep(
            name="structure",
            outcome="reject",
            detail=f"too long ({info.duration_s:.0f} s, limit {max_s} s)",
        )
    if kind == "audio" and not info.has_audio:
        return IntakeStep(name="structure", outcome="reject", detail="no audio stream")
    if kind == "video" and not info.has_video:
        return IntakeStep(name="structure", outcome="reject", detail="no video stream")
    if kind == "video" and not info.has_audio:
        return IntakeStep(name="structure", outcome="flag", detail="no audio to transcribe")
    return IntakeStep(name="structure", outcome="ok", detail=info.format_name)


def media_steps(kind: str, path: Path, mime: str, head: bytes, max_s: int) -> list[IntakeStep]:
    """Step 4 for video and audio; every failure is a reject (fail closed)."""
    if any(m in head for m in PLAYLIST_MARKERS):
        return [IntakeStep(name="structure", outcome="reject", detail="playlist marker in media")]
    demuxer = demuxer_for(mime)
    if demuxer is None:
        return [IntakeStep(name="structure", outcome="reject", detail=f"not media: {mime}")]
    try:
        info = probe_media(path, demuxer)
    except MediaProbeError as exc:
        return [IntakeStep(name="structure", outcome="reject", detail=str(exc)[:200])]
    return [check_media(info, max_s, kind)]
