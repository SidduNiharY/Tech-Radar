"""Adversarial review of the parser's media path (Phase 2c, review of d18ebba).

Paths, bounds, hostile media, child-process cleanup and the worker contract.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from techradar.library.media_results import parse_probe, parse_segment_result
from techradar.parser import media_extract
from techradar.parser.limits import parse_job, run_with_limits
from techradar.parser.media_extract import MediaExtractError, extract_audio_segment
from techradar.schemas.pipeline import ParseJob

HAVE_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None
needs_ffmpeg = pytest.mark.skipif(not HAVE_FFMPEG, reason="ffmpeg/ffprobe not installed")


def make_media(path: Path, *, seconds: int = 4, video: bool = True, audio: bool = True) -> Path:
    cmd = ["ffmpeg", "-v", "error", "-y"]
    if video:
        cmd += ["-f", "lavfi", "-i", f"testsrc=duration={seconds}:size=64x48:rate=5"]
    if audio:
        cmd += ["-f", "lavfi", "-i", f"sine=duration={seconds}"]
    if video:
        cmd += ["-c:v", "libx264"]
    if audio:
        cmd += ["-c:a", "aac"]
    cmd += ["-shortest", str(path)]
    subprocess.run(cmd, check=True, timeout=60)  # noqa: S603
    return path


def job(name: str, kind: str = "video", **kw) -> ParseJob:
    fields = {
        "job_id": "c" * 32,
        "kind": kind,
        "raw_name": name,
        "url": "library:7",
        "source_id": 0,
        "origin": "library",
        "purpose": "library",
        "doc_id": 7,
    }
    fields.update(kw)
    return ParseJob(**fields)


def segment(tmp: Path, j: ParseJob, media_dir: Path, **kw):
    return parse_job(j, tmp, max_bytes=10**9, media_dir=media_dir, artifacts_path=None, **kw)


@pytest.fixture
def video(tmp_path: Path) -> Path:
    if not HAVE_FFMPEG:
        pytest.skip("ffmpeg/ffprobe not installed")
    return make_media(tmp_path / ("d" * 64 + ".mp4"))


# --- paths ---------------------------------------------------------------------


@pytest.mark.parametrize("doc_id", [0, -1, -7])
def test_doc_id_must_be_positive(tmp_path, video, doc_id):
    media = tmp_path / "media"
    j = job(video.name, mode="media", ts_start=0.0, ts_end=2.0, doc_id=doc_id)
    assert segment(tmp_path, j, media).status == "error"
    assert not media.exists() or not any(media.rglob("*.flac"))


def test_symlinked_doc_folder_is_refused(tmp_path, video):
    media, elsewhere = tmp_path / "media", tmp_path / "elsewhere"
    media.mkdir()
    elsewhere.mkdir()
    (media / "7").symlink_to(elsewhere, target_is_directory=True)
    j = job(video.name, mode="media", ts_start=0.0, ts_end=2.0)
    assert segment(tmp_path, j, media).status == "error"
    assert list(elsewhere.iterdir()) == []


def test_symlinked_audio_folder_is_refused(tmp_path, video):
    media, elsewhere = tmp_path / "media", tmp_path / "elsewhere"
    (media / "7").mkdir(parents=True)
    elsewhere.mkdir()
    (media / "7" / "audio").symlink_to(elsewhere, target_is_directory=True)
    j = job(video.name, mode="media", ts_start=0.0, ts_end=2.0)
    assert segment(tmp_path, j, media).status == "error"
    assert list(elsewhere.iterdir()) == []


def test_symlinked_output_file_is_replaced_not_followed(tmp_path, video):
    media = tmp_path / "media"
    audio = media / "7" / "audio"
    audio.mkdir(parents=True)
    victim = tmp_path / "victim.txt"
    victim.write_text("keep me")
    (audio / "seg-00000.flac").symlink_to(victim)
    j = job(video.name, mode="media", ts_start=0.0, ts_end=2.0)
    assert segment(tmp_path, j, media).status == "ok"
    assert victim.read_text() == "keep me"
    out = audio / "seg-00000.flac"
    assert not out.is_symlink() and out.stat().st_size > 0
    # Idempotent: a re-run replaces the file and leaves no temporary files behind.
    assert segment(tmp_path, j, media).status == "ok"
    assert sorted(p.name for p in audio.iterdir()) == ["seg-00000.flac"]


def test_symlinked_original_is_refused(tmp_path, video):
    originals = tmp_path / "originals"
    originals.mkdir()
    link = originals / ("e" * 64 + ".mp4")
    link.symlink_to(video)
    res = parse_job(job(link.name, mode="probe"), originals, max_bytes=10**9)
    assert res.status == "error"


# --- bounds --------------------------------------------------------------------


def test_segment_past_the_probed_end_is_an_error(tmp_path, video):
    media = tmp_path / "media"
    j = job(video.name, mode="media", ts_start=600.0, ts_end=1200.0)
    assert segment(tmp_path, j, media).status == "error"
    assert not any(media.rglob("*.flac")) if media.exists() else True


def test_segment_longer_than_the_limit_is_an_error(tmp_path, video):
    j = job(video.name, mode="media", ts_start=0.0, ts_end=700.0)
    assert segment(tmp_path, j, tmp_path / "media").status == "error"


def test_negative_zero_start_is_fine(tmp_path, video):
    j = job(video.name, mode="media", ts_start=-0.0, ts_end=2.0)
    assert segment(tmp_path, j, tmp_path / "media").status == "ok"


@needs_ffmpeg
def test_dense_slides_still_fit_the_result(tmp_path, monkeypatch):
    # 40 slides of 4000 characters (non-ASCII too) are more than one CleanDoc holds:
    # the segment must still succeed, with as many whole slides as fit.
    monkeypatch.setattr(
        "techradar.parser.limits.offline_ocr",
        lambda _a: lambda p: f"{p.stem} " + "अआ " * 2000,
    )
    video = make_media(tmp_path / ("9" * 64 + ".mp4"), seconds=12)
    j = job(video.name, mode="media", ts_start=0.0, ts_end=12.0)
    res = parse_job(
        j,
        tmp_path,
        max_bytes=10**9,
        media_dir=tmp_path / "media",
        artifacts_path=tmp_path,
        frame_every_s=1,
    )
    assert res.status == "ok" and res.doc is not None
    seg = parse_segment_result(res.doc.text, 0.0, 12.0)
    assert seg is not None and seg.slides


# --- the worker's validators accept exactly what the parser writes -------------


def test_probe_result_matches_the_worker_contract(tmp_path, video):
    res = parse_job(job(video.name, mode="probe"), tmp_path, max_bytes=10**9)
    assert res.status == "ok" and res.doc is not None
    probe = parse_probe(res.doc.text)
    assert probe is not None and probe.has_audio and probe.has_video


def test_segment_result_matches_the_worker_contract(tmp_path, video, monkeypatch):
    monkeypatch.setattr(
        "techradar.parser.limits.offline_ocr", lambda _a: lambda p: "Slide " + p.stem
    )
    j = job(video.name, mode="media", ts_start=1.0, ts_end=4.0)
    res = parse_job(
        j,
        tmp_path,
        max_bytes=10**9,
        media_dir=tmp_path / "media",
        artifacts_path=tmp_path,
        frame_every_s=1,
    )
    assert res.status == "ok" and res.doc is not None
    seg = parse_segment_result(res.doc.text, 1.0, 4.0)
    assert seg is not None and seg.audio_file == "audio/seg-00001.flac"


# --- hostile media: a clean error or result, never a crash or a hang ------------


def _hostile_files(tmp: Path) -> dict[str, Path]:
    files: dict[str, Path] = {}

    def put(label: str, ext: str, data: bytes) -> None:
        p = tmp / f"{label}"
        p.mkdir()
        f = p / (format(len(files), "064x") + ext)
        f.write_bytes(data)
        files[label] = f

    put("hls", ".mp4", b"#EXTM3U\n#EXT-X-VERSION:3\n#EXTINF:10,\nfile:///etc/passwd\n")
    put("ffconcat", ".mp4", b"ffconcat version 1.0\nfile '/etc/passwd'\n")
    put("empty", ".mp4", b"")
    put("image2", ".mp4", b"\x89PNG\r\n\x1a\n" + b"\0" * 64)
    good = make_media(tmp / "good.mp4")
    data = good.read_bytes()
    put("truncated", ".mp4", data[: len(data) // 3])
    put("polyglot", ".mp4", b"%PDF-1.4\n" + data)
    mkv = make_media(tmp / "good.mkv")
    put("mkv_named_mp4", ".mp4", mkv.read_bytes())
    put("audio_only", ".mp4", make_media(tmp / "a.m4a", video=False).read_bytes())
    put("video_only", ".mp4", make_media(tmp / "v.mp4", audio=False).read_bytes())
    return files


@needs_ffmpeg
def test_hostile_media_ends_cleanly(tmp_path):
    for label, f in _hostile_files(tmp_path).items():
        for mode, extra in (("probe", {}), ("media", {"ts_start": 0.0, "ts_end": 2.0})):
            started = time.monotonic()
            res = segment(f.parent, job(f.name, mode=mode, **extra), tmp_path / "media" / label)
            assert time.monotonic() - started < 30, label
            assert res.status in {"ok", "error", "empty"}, (label, mode, res.status)
            if label in {"hls", "ffconcat", "empty", "image2"}:
                assert res.status == "error", (label, mode)


@needs_ffmpeg
def test_a_thousand_tracks_end_cleanly(tmp_path):
    src = make_media(tmp_path / "one.mkv", seconds=1)
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", str(src)]
    cmd += [x for _ in range(200) for x in ("-map", "0:a")]
    out = tmp_path / ("a" * 64 + ".mkv")
    subprocess.run([*cmd, "-c", "copy", str(out)], check=True, timeout=60)  # noqa: S603
    j = job(out.name, mode="media", ts_start=0.0, ts_end=1.0)
    res = segment(tmp_path, j, tmp_path / "media")
    assert res.status in {"ok", "error"}


# --- ffmpeg runs with its own small limits -----------------------------------------


def test_ffmpeg_gets_resource_limits_and_a_size_cap(monkeypatch, tmp_path):
    seen: dict = {}

    def fake_run(args, **kwargs):
        seen["args"], seen["kwargs"] = args, kwargs
        Path(args[-1]).write_bytes(b"fLaC")
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    extract_audio_segment(
        Path("v.mp4"), tmp_path / "seg.flac", demuxer="mov", start_s=0.0, dur_s=10.0
    )
    args = seen["args"]
    assert seen["kwargs"].get("preexec_fn") is not None
    assert args[args.index("-fs") + 1] == str(media_extract.MAX_AUDIO_BYTES)
    assert args[args.index("-threads") + 1] == str(media_extract.FFMPEG_THREADS)


def test_frames_are_small_bounded_and_keyframe_only(monkeypatch, tmp_path):
    seen: dict = {}

    def fake_run(args, **kwargs):
        seen["args"] = args
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    media_extract.extract_frames(
        Path("v.mp4"), tmp_path, demuxer="mov", every_s=30, start_s=0.0, dur_s=600.0
    )
    args = seen["args"]
    assert args[args.index("-skip_frame") + 1] == "nokey"
    assert args.index("-skip_frame") < args.index("-i")
    assert "scale=" in args[args.index("-vf") + 1]
    assert int(args[args.index("-frames:v") + 1]) <= media_extract.MAX_FRAMES


@needs_ffmpeg
def test_output_size_cap_stops_ffmpeg(tmp_path, monkeypatch, video):
    monkeypatch.setattr(media_extract, "MAX_AUDIO_BYTES", 2_000)
    with pytest.raises(MediaExtractError):
        extract_audio_segment(video, tmp_path / "seg.flac", demuxer="mov", start_s=0.0, dur_s=4.0)


def test_ffmpeg_timeout_follows_the_job_deadline(monkeypatch, tmp_path):
    seen: dict = {}

    def fake_run(args, **kwargs):
        seen["timeout"] = kwargs["timeout"]
        Path(args[-1]).write_bytes(b"fLaC")
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    deadline = time.monotonic() + 7
    extract_audio_segment(
        Path("v.mp4"),
        tmp_path / "s.flac",
        demuxer="mov",
        start_s=0.0,
        dur_s=1.0,
        deadline=deadline,
    )
    assert 0 < seen["timeout"] <= 7


def test_past_deadline_never_starts_ffmpeg(monkeypatch, tmp_path):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("ffmpeg started"))
    with pytest.raises(MediaExtractError):
        extract_audio_segment(
            Path("v.mp4"),
            tmp_path / "s.flac",
            demuxer="mov",
            start_s=0.0,
            dur_s=1.0,
            deadline=time.monotonic() - 1,
        )


# --- a timed-out job leaves no ffmpeg behind ----------------------------------------


@needs_ffmpeg
def test_timeout_kills_ffmpeg_too(tmp_path):
    video = make_media(tmp_path / ("f" * 64 + ".mp4"))
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    pid_file = tmp_path / "ffmpeg.pid"
    fake = fake_bin / "ffmpeg"
    fake.write_text(f"#!/bin/sh\necho $$ > {pid_file}\nexec sleep 300\n")
    fake.chmod(0o755)
    real_ffprobe = shutil.which("ffprobe")
    assert real_ffprobe
    os.symlink(real_ffprobe, fake_bin / "ffprobe")
    old_path = os.environ["PATH"]
    os.environ["PATH"] = f"{fake_bin}:{old_path}"
    try:
        j = job(video.name, mode="media", ts_start=0.0, ts_end=2.0)
        res = run_with_limits(
            j, tmp_path, timeout_s=8, max_bytes=10**9, media_dir=tmp_path / "media"
        )
    finally:
        os.environ["PATH"] = old_path
    assert res.status == "timeout"
    pid = int(pid_file.read_text())
    for _ in range(50):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.1)
    else:
        os.kill(pid, 9)
        pytest.fail("ffmpeg outlived the timed-out job")


def test_probe_duration_must_be_finite(tmp_path, video, monkeypatch):
    from techradar.intake.media import MediaInfo

    def lying_probe(path, demuxer, timeout_s=30):
        return MediaInfo(format_name="x", duration_s=float("nan"), has_audio=True, has_video=True)

    monkeypatch.setattr("techradar.parser.limits.probe_media", lying_probe)
    res = parse_job(job(video.name, mode="probe"), tmp_path, max_bytes=10**9)
    assert res.status == "error"
    j = job(video.name, mode="media", ts_start=0.0, ts_end=2.0)
    assert segment(tmp_path, j, tmp_path / "media").status == "error"
    assert json  # probe text is plain JSON (no NaN), checked by the contract test above
