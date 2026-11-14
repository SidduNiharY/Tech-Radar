"""Audio, frames and slide text from videos, inside the parser sandbox.

Phase 2c Task 5 (SEC-44). ffmpeg runs only after the gateway's media check,
with list arguments (no shell), only the `file` protocol, the container
allowlist, the input demuxer forced from the file's own signature, and a
timeout. Transcription comes later (phase 6, D38).
"""

from __future__ import annotations

import contextlib
import math
import os
import resource
import subprocess
import time
from collections.abc import Callable, Sequence
from pathlib import Path

from pydantic import BaseModel

from techradar.intake.media import DEMUXER_WHITELIST
from techradar.security.text import sanitize_text

_ALLOWED_DEMUXERS = frozenset(DEMUXER_WHITELIST.split(","))
MAX_SLIDE_CHARS = 4000
# ffmpeg gets its own small limits (it never needs the OCR models' address space):
# decoding 1080p H.264 with two threads stays far below these.
FFMPEG_AS_BYTES = 3_000_000_000
FFMPEG_THREADS = 2
# Largest file one ffmpeg run may write. A 600 s mono 16 kHz FLAC is about 10-15 MB;
# a frame PNG at FRAME_HEIGHT is well under 1 MB.
MAX_AUDIO_BYTES = 40_000_000
MAX_FILE_BYTES = 64_000_000
# Slide frames: low resolution (enough for slide text), keyframes only, a fixed count.
FRAME_HEIGHT = 720
MAX_FRAMES = 21
FRAME_TIMEOUT_S = 15.0


class MediaExtractError(RuntimeError):
    """ffmpeg could not extract from the file."""


class SlideText(BaseModel):
    ts_s: float
    text: str


def _limit_ffmpeg() -> None:
    """Runs in the ffmpeg child before exec: memory, written-file size, no core dumps.

    Lowering a limit always works on Linux (the parser); macOS refuses some, so a
    refusal there is ignored rather than making ffmpeg unusable in development.
    """
    for name, value in (
        ("RLIMIT_CORE", 0),
        ("RLIMIT_FSIZE", MAX_FILE_BYTES),
        ("RLIMIT_AS", FFMPEG_AS_BYTES),
    ):
        which = getattr(resource, name, None)
        if which is None:
            continue
        with contextlib.suppress(ValueError, OSError):
            _soft, hard = resource.getrlimit(which)
            target = value if hard == resource.RLIM_INFINITY else min(value, hard)
            resource.setrlimit(which, (target, target if name != "RLIMIT_AS" else hard))


def _input_args(
    src: Path,
    demuxer: str,
    start_s: float = 0.0,
    dur_s: float | None = None,
    decoder_opts: Sequence[str] = (),
) -> list[str]:
    if demuxer not in _ALLOWED_DEMUXERS:
        raise MediaExtractError(f"demuxer not allowed: {demuxer!r}")
    window = ["-ss", f"{start_s:.3f}"] if start_s > 0 else []
    if dur_s is not None:
        window += ["-t", f"{dur_s:.3f}"]
    return [
        "ffmpeg",
        "-nostdin",
        "-v",
        "error",
        "-threads",
        str(FFMPEG_THREADS),
        "-protocol_whitelist",
        "file",
        "-format_whitelist",
        DEMUXER_WHITELIST,
        *window,
        *decoder_opts,
        "-f",
        demuxer,
        "-i",
        str(src),
    ]


def _timeout(timeout_s: float, deadline: float | None) -> float:
    """The smaller of timeout_s and the time left before the job's deadline."""
    if deadline is not None:
        timeout_s = min(timeout_s, deadline - time.monotonic())
    if timeout_s <= 1:
        raise MediaExtractError("no time left for ffmpeg")
    return timeout_s


def _run(args: list[str], timeout_s: float) -> None:
    try:
        res = subprocess.run(  # noqa: S603
            args,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
            preexec_fn=_limit_ffmpeg,  # noqa: PLW1509 (runs before any OCR thread starts)
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
        raise MediaExtractError(f"ffmpeg failed: {type(exc).__name__}") from exc
    if res.returncode != 0:
        raise MediaExtractError(
            f"ffmpeg refused the file ({res.returncode}): {(res.stderr or '').strip()[:200]}"
        )


def extract_audio_parts(
    src: Path, out_dir: Path, *, demuxer: str, part_s: int = 600, timeout_s: int = 900
) -> list[Path]:
    """Mono 16 kHz FLAC parts of part_s seconds (part-000.flac, part-001.flac, ...)."""
    args = _input_args(src, demuxer)  # validates the demuxer before touching disk
    out_dir.mkdir(parents=True, exist_ok=True)
    args += [
        "-vn",
        "-sn",
        "-dn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-f",
        "segment",
        "-segment_time",
        str(part_s),
        "-c:a",
        "flac",
        str(out_dir / "part-%03d.flac"),
    ]
    _run(args, timeout_s)
    return sorted(out_dir.glob("part-*.flac"))


def extract_audio_segment(
    src: Path,
    out_file: Path,
    *,
    demuxer: str,
    start_s: float,
    dur_s: float,
    timeout_s: float = 100,
    deadline: float | None = None,
) -> Path:
    """Mono 16 kHz FLAC of one segment (a media job stays under the parser's 120 s).

    ffmpeg writes a fresh temporary name next to out_file, which then replaces it
    (os.replace never follows a symlink planted at out_file). The caller checks that
    out_file's folder is a real folder.
    """
    args = _input_args(src, demuxer, start_s, dur_s)
    timeout = _timeout(timeout_s, deadline)
    tmp = out_file.with_name(f".{out_file.stem}.{os.getpid()}.{time.monotonic_ns()}.tmp")
    args += [
        "-map",
        "0:a:0",
        "-vn",
        "-sn",
        "-dn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "flac",
        "-fs",
        str(MAX_AUDIO_BYTES),
        "-f",
        "flac",
        "-n",
        str(tmp),
    ]
    try:
        _run(args, timeout)
        if not tmp.is_file() or tmp.is_symlink() or tmp.stat().st_size == 0:
            raise MediaExtractError("no audio in segment")
        if tmp.stat().st_size >= MAX_AUDIO_BYTES:
            raise MediaExtractError("audio segment too large")
        os.replace(tmp, out_file)
    finally:
        tmp.unlink(missing_ok=True)
    return out_file


def extract_frames(
    src: Path,
    out_dir: Path,
    *,
    demuxer: str,
    every_s: int = 30,
    timeout_s: float = 900,
    start_s: float = 0.0,
    dur_s: float | None = None,
    deadline: float | None = None,
) -> list[tuple[float, Path]]:
    """One low-resolution PNG every every_s seconds, each with its timestamp in seconds.

    One short ffmpeg run per timestamp: it seeks to the keyframe at or before it and
    decodes only that keyframe, so the cost does not grow with the segment's length
    or with a hostile keyframe interval. At most MAX_FRAMES. A frame ffmpeg cannot
    give is skipped (slides are best effort; the audio already succeeded).
    """
    if demuxer not in _ALLOWED_DEMUXERS:
        raise MediaExtractError(f"demuxer not allowed: {demuxer!r}")
    if every_s <= 0:
        raise MediaExtractError("every_s must be positive")
    out_dir.mkdir(parents=True, exist_ok=True)
    n = MAX_FRAMES
    if dur_s is not None:
        n = min(MAX_FRAMES, max(1, math.ceil(dur_s / every_s)))
    frames: list[tuple[float, Path]] = []
    for index in range(n):
        ts = start_s + float(index * every_s)
        out = out_dir / f"frame-{index + 1:05d}.png"
        args = _input_args(
            src, demuxer, ts, None, decoder_opts=("-noaccurate_seek", "-skip_frame", "nokey")
        )
        args += [
            "-map",
            "0:v:0",
            "-an",
            "-sn",
            "-dn",
            "-frames:v",
            "1",
            "-fps_mode",
            "passthrough",
            "-vf",
            f"scale=-2:'min({FRAME_HEIGHT},ih)'",
            "-n",
            str(out),
        ]
        try:
            _run(args, _timeout(min(timeout_s, FRAME_TIMEOUT_S), deadline))
        except MediaExtractError:
            if deadline is not None and deadline - time.monotonic() <= 1:
                break
            continue
        if out.is_file() and not out.is_symlink() and out.stat().st_size > 0:
            frames.append((ts, out))
    return frames


def _norm(text: str) -> str:
    return " ".join(text.lower().split())


def slide_text(
    frames: Sequence[tuple[float, Path]],
    ocr: Callable[[Path], str],
    deadline: float | None = None,
) -> list[SlideText]:
    """OCR each frame; drop frames with no text and repeats of the previous slide.

    Stops at the deadline with the slides read so far (the audio matters more).
    """
    slides: list[SlideText] = []
    previous = ""
    for ts, path in frames:
        if deadline is not None and time.monotonic() >= deadline:
            break
        text = sanitize_text(ocr(path) or "").strip()[:MAX_SLIDE_CHARS]
        if not text or _norm(text) == previous:
            continue
        previous = _norm(text)
        slides.append(SlideText(ts_s=ts, text=text))
    return slides
