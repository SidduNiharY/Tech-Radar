"""Phase 2c Task 5: audio, frames and slide text from videos, in the sandbox."""

import shutil
import subprocess
from pathlib import Path

import pytest

from techradar.parser.media_extract import (
    MediaExtractError,
    SlideText,
    extract_audio_parts,
    extract_frames,
    slide_text,
)

HAVE_FFMPEG = shutil.which("ffmpeg") is not None
needs_ffmpeg = pytest.mark.skipif(not HAVE_FFMPEG, reason="ffmpeg not installed")


def make_video(path: Path, seconds: int = 3) -> Path:
    subprocess.run(  # noqa: S603
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"testsrc=duration={seconds}:size=64x48:rate=5",
            "-f",
            "lavfi",
            "-i",
            f"sine=duration={seconds}",
            "-shortest",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            str(path),
        ],
        check=True,
        timeout=60,
    )
    return path


def capture(monkeypatch):
    seen: dict = {}

    def fake_run(args, **kwargs):
        seen["args"], seen["kwargs"] = args, kwargs
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    return seen


def test_extract_audio_uses_list_args_and_whitelists(monkeypatch, tmp_path):
    seen = capture(monkeypatch)
    extract_audio_parts(Path("v.mp4"), tmp_path, demuxer="mov")
    args = seen["args"]
    assert isinstance(args, list) and "shell" not in seen["kwargs"]
    assert args[args.index("-protocol_whitelist") + 1] == "file"
    assert args[args.index("-format_whitelist") + 1] == "mov,matroska,mp3,wav,ogg"
    assert args[args.index("-f") + 1] == "mov"  # the input demuxer is forced
    assert seen["kwargs"]["timeout"] == 900
    assert "-nostdin" in args and "-vn" in args


def test_extract_frames_uses_list_args_and_whitelists(monkeypatch, tmp_path):
    seen = capture(monkeypatch)
    extract_frames(Path("v.mp4"), tmp_path, demuxer="mov", every_s=30)
    args = seen["args"]
    assert args[args.index("-protocol_whitelist") + 1] == "file"
    assert args[args.index("-f") + 1] == "mov"
    assert "fps=1/30" in " ".join(args)


def test_unknown_demuxer_refused(tmp_path):
    with pytest.raises(MediaExtractError):
        extract_audio_parts(Path("v.mp4"), tmp_path, demuxer="hls")


def test_ffmpeg_failure_raises(monkeypatch, tmp_path):
    def failing(args, **kwargs):
        return subprocess.CompletedProcess(args, 1, stdout="", stderr="bad input")

    monkeypatch.setattr(subprocess, "run", failing)
    with pytest.raises(MediaExtractError):
        extract_audio_parts(Path("v.mp4"), tmp_path, demuxer="mov")


@needs_ffmpeg
def test_real_audio_parts_and_frames(tmp_path):
    video = make_video(tmp_path / "v.mp4", seconds=3)
    parts = extract_audio_parts(video, tmp_path / "audio", demuxer="mov", part_s=2)
    assert [p.name for p in parts] == ["part-000.flac", "part-001.flac"]
    frames = extract_frames(video, tmp_path / "frames", demuxer="mov", every_s=1)
    assert frames and frames[0][0] == 0.0 and frames[1][0] == 1.0
    assert all(p.suffix == ".png" for _, p in frames)


def test_slide_text_drops_repeats_and_empties(tmp_path):
    texts = iter(["Deadlocks", "Deadlocks", "", "Banker's algorithm"])
    p = tmp_path / "f.png"
    s = slide_text([(0, p), (30, p), (60, p), (90, p)], ocr=lambda _: next(texts))
    assert [x.ts_s for x in s] == [0, 90]
    assert s[1] == SlideText(ts_s=90, text="Banker's algorithm")


def test_slide_text_is_capped():
    s = slide_text([(0.0, Path("x"))], ocr=lambda _: "word " * 2000)
    assert len(s[0].text) <= 4000
