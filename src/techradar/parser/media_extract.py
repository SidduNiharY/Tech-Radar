"""Audio, frames and slide text from videos, inside the parser sandbox.

Phase 2c Task 5 (SEC-44). ffmpeg runs only after the gateway's media check,
with list arguments (no shell), only the `file` protocol, the container
allowlist, the input demuxer forced from the file's own signature, and a
timeout. Transcription comes later (phase 6, D38).
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path

from pydantic import BaseModel

from techradar.intake.media import DEMUXER_WHITELIST
from techradar.security.text import sanitize_text

_ALLOWED_DEMUXERS = frozenset(DEMUXER_WHITELIST.split(","))
MAX_SLIDE_CHARS = 4000


class MediaExtractError(RuntimeError):
    """ffmpeg could not extract from the file."""


class SlideText(BaseModel):
    ts_s: float
    text: str


def _input_args(src: Path, demuxer: str) -> list[str]:
    if demuxer not in _ALLOWED_DEMUXERS:
        raise MediaExtractError(f"demuxer not allowed: {demuxer!r}")
    return [
        "ffmpeg",
        "-nostdin",
        "-v",
        "error",
        "-protocol_whitelist",
        "file",
        "-format_whitelist",
        DEMUXER_WHITELIST,
        "-f",
        demuxer,
        "-i",
        str(src),
    ]


def _run(args: list[str], timeout_s: int) -> None:
    try:
        res = subprocess.run(  # noqa: S603
            args, capture_output=True, text=True, timeout=timeout_s, check=False
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
        raise MediaExtractError(f"ffmpeg failed: {type(exc).__name__}") from exc
    if res.returncode != 0:
        raise MediaExtractError(f"ffmpeg refused the file: {(res.stderr or '').strip()[:200]}")


def extract_audio_parts(
    src: Path, out_dir: Path, *, demuxer: str, part_s: int = 600, timeout_s: int = 900
) -> list[Path]:
    """Mono 16 kHz FLAC parts of part_s seconds (part-000.flac, part-001.flac, ...)."""
    args = _input_args(src, demuxer)  # validates the demuxer before touching disk
    out_dir.mkdir(parents=True, exist_ok=True)
    args += [
        "-vn",
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


def extract_frames(
    src: Path, out_dir: Path, *, demuxer: str, every_s: int = 30, timeout_s: int = 900
) -> list[tuple[float, Path]]:
    """One PNG every every_s seconds, each with its timestamp in seconds."""
    args = _input_args(src, demuxer)
    out_dir.mkdir(parents=True, exist_ok=True)
    args += ["-an", "-vf", f"fps=1/{every_s}", str(out_dir / "frame-%05d.png")]
    _run(args, timeout_s)
    frames = []
    for path in sorted(out_dir.glob("frame-*.png")):
        index = int(re.sub(r"\D", "", path.stem))  # 1-based
        frames.append((float((index - 1) * every_s), path))
    return frames


def _norm(text: str) -> str:
    return " ".join(text.lower().split())


def slide_text(frames: Sequence[tuple[float, Path]], ocr: Callable[[Path], str]) -> list[SlideText]:
    """OCR each frame; drop frames with no text and repeats of the previous slide."""
    slides: list[SlideText] = []
    previous = ""
    for ts, path in frames:
        text = sanitize_text(ocr(path) or "").strip()[:MAX_SLIDE_CHARS]
        if not text or _norm(text) == previous:
            continue
        previous = _norm(text)
        slides.append(SlideText(ts_s=ts, text=text))
    return slides
