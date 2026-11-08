from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

from techradar.library.models import MediaInfo

MAX_VIDEO_DURATION_S = 14_400  # 4 hours
MAX_VIDEO_SIZE_BYTES = 4 * 1024 * 1024 * 1024  # 4 GB
MAX_AUDIO_SIZE_BYTES = 1 * 1024 * 1024 * 1024  # 1 GB

PLAYLIST_EXTENSIONS = frozenset({".m3u8", ".m3u", ".pls", ".asx", ".wax", ".wvx", ".cue"})
CONCAT_EXTENSIONS = frozenset({".concat", ".ffconcat"})
REMOTE_SCHEMES = (
    "http://",
    "https://",
    "rtmp://",
    "rtmps://",
    "rtsp://",
    "ftp://",
    "ftps://",
    "tcp://",
    "udp://",
    "gopher://",
    "data:",
)


class MediaLimitExceededError(ValueError):
    """Raised when a media file exceeds duration or size limits."""


class MediaSecurityError(ValueError):
    """Raised when a media file violates security constraints (playlists, URLs, concat)."""


def _validate_media_path_security(path: Path | str) -> None:
    """Validates that a media path is safe and local (SEC-44)."""
    path_str = str(path).strip()

    # Rejection of network URLs
    lower = path_str.lower()
    for scheme in REMOTE_SCHEMES:
        if lower.startswith(scheme):
            raise MediaSecurityError(f"Remote URLs are rejected (SEC-44): {path_str}")

    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", path_str):
        raise MediaSecurityError(f"Remote URLs are rejected (SEC-44): {path_str}")

    p = Path(path_str)
    suffix = p.suffix.lower()

    # Rejection of playlist extensions
    if suffix in PLAYLIST_EXTENSIONS:
        raise MediaSecurityError(f"Playlist extensions are rejected (SEC-44): {suffix}")

    # Rejection of concat lists
    if suffix in CONCAT_EXTENSIONS:
        raise MediaSecurityError(f"Concat lists are rejected (SEC-44): {suffix}")

    # Rejection of concat headers in file contents
    try:
        if p.is_file():
            with open(p, "rb") as f:
                header = f.read(512)
                if header.startswith(b"ffconcat") or b"#EXTM3U" in header:
                    raise MediaSecurityError("Concat list or playlist content rejected (SEC-44)")
    except OSError:
        pass


def validate_media_limits(
    path: Path | str | None = None,
    *,
    duration_s: float | None = None,
    is_audio: bool = False,
    file_size: int | None = None,
) -> None:
    """Enforces video duration <= 14,400s (4h), video size <= 4GB, audio size <= 1GB."""
    if duration_s is not None and duration_s > MAX_VIDEO_DURATION_S:
        raise MediaLimitExceededError(
            f"Media duration {duration_s}s exceeds maximum {MAX_VIDEO_DURATION_S}s"
        )

    size = file_size
    if size is None and path is not None:
        p = Path(path)
        try:
            if p.is_file():
                size = p.stat().st_size
        except OSError:
            pass

    if size is not None:
        if is_audio:
            if size > MAX_AUDIO_SIZE_BYTES:
                msg = f"Audio size {size} bytes exceeds limit {MAX_AUDIO_SIZE_BYTES} (1GB)"
                raise MediaLimitExceededError(msg)
        else:
            if size > MAX_VIDEO_SIZE_BYTES:
                msg = f"Video size {size} bytes exceeds limit {MAX_VIDEO_SIZE_BYTES} (4GB)"
                raise MediaLimitExceededError(msg)


check_media_limits = validate_media_limits


def build_ffmpeg_audio_extract_args(
    video_path: Path | str,
    output_audio: Path | str,
    *,
    duration_s: float | None = None,
    file_size: int | None = None,
) -> list[str]:
    """Builds ffmpeg arguments for audio extraction with SEC-44 sandboxing."""
    _validate_media_path_security(video_path)
    validate_media_limits(
        video_path,
        duration_s=duration_s,
        is_audio=False,
        file_size=file_size,
    )

    return [
        "ffmpeg",
        "-nostdin",
        "-protocol_whitelist",
        "file",
        "-i",
        str(video_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        str(output_audio),
    ]


def build_ffmpeg_frame_extract_args(
    video_path: Path | str,
    output_dir: Path | str,
    fps: float = 1 / 60.0,
    *,
    duration_s: float | None = None,
    file_size: int | None = None,
) -> list[str]:
    """Builds ffmpeg arguments for frame extraction with SEC-44 sandboxing."""
    _validate_media_path_security(video_path)
    validate_media_limits(
        video_path,
        duration_s=duration_s,
        is_audio=False,
        file_size=file_size,
    )

    out_pattern = str(Path(output_dir) / "frame_%04d.png")
    return [
        "ffmpeg",
        "-nostdin",
        "-protocol_whitelist",
        "file",
        "-i",
        str(video_path),
        "-vf",
        f"fps={fps}",
        out_pattern,
    ]


def probe_media(path: Path | str, timeout_s: int = 30) -> MediaInfo:
    """Probes media metadata using ffprobe with protocol_whitelist file."""
    _validate_media_path_security(path)
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"Media file not found: {p}")

    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-protocol_whitelist",
        "file",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(p),
    ]
    try:
        res = subprocess.run(  # noqa: S603
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=True,
        )
        data: dict[str, Any] = json.loads(res.stdout)
    except Exception as exc:
        raise ValueError(f"Failed to probe media {p}: {exc}") from exc

    fmt = data.get("format", {})
    format_name = str(fmt.get("format_name", ""))
    duration_s = float(fmt.get("duration", 0.0))
    size_bytes = int(fmt.get("size", 0))

    streams = data.get("streams", [])
    has_audio = any(s.get("codec_type") == "audio" for s in streams)
    has_video = any(s.get("codec_type") == "video" for s in streams)

    validate_media_limits(
        p,
        duration_s=duration_s,
        is_audio=(has_audio and not has_video),
        file_size=size_bytes,
    )

    return MediaInfo(
        format_name=format_name,
        duration_s=duration_s,
        has_audio=has_audio,
        has_video=has_video,
        size_bytes=size_bytes,
    )
