"""Phase 2c Task 3: media checks with ffprobe (Intake Gateway step 4)."""

import shutil
import subprocess
from datetime import date
from pathlib import Path

import pytest
import yaml

from techradar.intake.av import AvResult
from techradar.intake.gateway import gate_job
from techradar.intake.media import (
    ALLOWED_CONTAINERS,
    MediaInfo,
    MediaProbeError,
    check_media,
    demuxer_for,
    probe_media,
)
from techradar.schemas.pipeline import CleanDoc, ParseJob, ParseResult

from .library_fixtures import FFCONCAT, HLS_PLAYLIST, MP3_HEAD

HAVE_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None
needs_ffmpeg = pytest.mark.skipif(not HAVE_FFMPEG, reason="ffmpeg/ffprobe not installed")
LIMITS = yaml.safe_load(Path("infra/intake/limits.yaml").read_text())
TODAY = date(2026, 11, 13)


def make_video(path: Path, *, seconds: int = 2, audio: bool = True) -> Path:
    cmd = [
        "ffmpeg",
        "-v",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"testsrc=duration={seconds}:size=64x48:rate=5",
    ]
    if audio:
        cmd += ["-f", "lavfi", "-i", f"sine=duration={seconds}", "-shortest", "-c:a", "aac"]
    cmd += ["-c:v", "libx264", str(path)]
    subprocess.run(cmd, check=True, timeout=60)  # noqa: S603
    return path


def test_probe_uses_list_args_whitelists_and_a_forced_demuxer(monkeypatch):
    seen = {}

    def fake_run(args, **kwargs):
        seen["args"], seen["kwargs"] = args, kwargs
        return subprocess.CompletedProcess(
            args, 0, stdout='{"format": {}, "streams": []}', stderr=""
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    probe_media(Path("x.mp4"), "mov")
    args = seen["args"]
    assert isinstance(args, list) and "shell" not in seen["kwargs"]
    assert args[args.index("-protocol_whitelist") + 1] == "file"
    assert args[args.index("-format_whitelist") + 1] == "mov,matroska,mp3,wav,ogg"
    assert args[args.index("-f") + 1] == "mov"
    assert seen["kwargs"]["timeout"] == 30


@pytest.mark.parametrize(
    ("mime", "demuxer"),
    [
        ("video/mp4", "mov"),
        ("video/quicktime", "mov"),
        ("audio/mp4", "mov"),
        ("video/webm", "matroska"),
        ("video/x-matroska", "matroska"),
        ("audio/mpeg", "mp3"),
        ("audio/wav", "wav"),
        ("audio/ogg", "ogg"),
    ],
)
def test_demuxer_comes_from_the_detected_type(mime, demuxer):
    assert demuxer_for(mime) == demuxer


def test_unknown_type_has_no_demuxer():
    assert demuxer_for("application/vnd.apple.mpegurl") is None


def test_check_media_rules():
    ok = MediaInfo(
        format_name="mov,mp4,m4a,3gp,3g2,mj2", duration_s=60, has_audio=True, has_video=True
    )
    assert check_media(ok, 14_400, "video").outcome == "ok"
    for bad in ["hls", "concat", "applehttp", "image2"]:
        assert (
            check_media(ok.model_copy(update={"format_name": bad}), 14_400, "video").outcome
            == "reject"
        )
    assert (
        check_media(ok.model_copy(update={"duration_s": 15_000}), 14_400, "video").outcome
        == "reject"
    )
    assert check_media(ok.model_copy(update={"duration_s": 0}), 14_400, "video").outcome == "reject"
    mute = ok.model_copy(update={"has_audio": False})
    step = check_media(mute, 14_400, "video")
    assert step.outcome == "flag" and step.detail == "no audio to transcribe"
    assert check_media(mute, 14_400, "audio").outcome == "reject"
    assert "mov,mp4,m4a,3gp,3g2,mj2" in ALLOWED_CONTAINERS


@needs_ffmpeg
def test_real_video_probes(tmp_path):
    info = probe_media(make_video(tmp_path / "short.mp4"), "mov")
    assert info.has_video and info.has_audio and 1.5 < info.duration_s < 2.5


@needs_ffmpeg
@pytest.mark.parametrize("body", [HLS_PLAYLIST, FFCONCAT])
def test_playlists_fail_to_probe_as_media(tmp_path, body):
    p = tmp_path / "playlist.mp4"
    p.write_bytes(body)
    with pytest.raises(MediaProbeError):
        probe_media(p, "mov")


class FakeAv:
    def scan(self, path: Path) -> AvResult:
        return AvResult(status="clean", db_date=TODAY)


def gate(tmp_path: Path, kind: str, ext: str, build) -> ParseResult:
    raw = tmp_path / "raw"
    raw.mkdir(exist_ok=True)
    name = "b" * 64 + "." + ext
    build(raw / name)
    job = ParseJob(
        job_id="a" * 32,
        kind=kind,
        raw_name=name,
        url="library:x",
        source_id=0,
        origin="library",
        purpose="library",
        mode="media",
    )

    def parse(j: ParseJob) -> ParseResult:
        doc = CleanDoc(url="library:x", title="t", text="media ok", lang="en")
        return ParseResult(job_id=j.job_id, kind=j.kind, status="ok", doc=doc)

    return gate_job(
        job,
        raw,
        tmp_path / "q",
        av=FakeAv(),
        allowed_hosts=frozenset(),
        limits=LIMITS,
        parse=parse,
        today=TODAY,
    )


@needs_ffmpeg
def test_real_video_passes_the_gateway(tmp_path):
    res = gate(tmp_path, "video", "mp4", lambda p: make_video(p))
    assert res.status == "ok"
    assert any(s.name == "structure" and s.outcome == "ok" for s in res.intake.steps)


def test_media_with_an_embedded_playlist_marker_rejected(tmp_path):
    # Detected as MP3 by its ID3 tag, but a playlist follows: refused before probing.
    res = gate(tmp_path, "audio", "mp3", lambda p: p.write_bytes(MP3_HEAD + b"\n" + HLS_PLAYLIST))
    assert res.status == "rejected"


def test_missing_ffprobe_fails_closed(tmp_path, monkeypatch):
    def no_binary(*a, **k):
        raise FileNotFoundError("ffprobe")

    monkeypatch.setattr(subprocess, "run", no_binary)
    with pytest.raises(MediaProbeError):
        probe_media(tmp_path / "x.mp4", "mov")
