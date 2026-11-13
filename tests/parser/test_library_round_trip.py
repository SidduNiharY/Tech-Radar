"""Library jobs through the real parser entry points (Opus review of 2a63953).

The bulk tests wrote results by hand, which hid two breaks: results never
carried the job's purpose, and library files were read from data/raw.
"""

import hashlib
import json
import shutil
import subprocess
from datetime import date
from pathlib import Path

import pytest
import yaml

from techradar.intake.av import AvResult
from techradar.parser.limits import MODEL_AS_BYTES, address_space_for, parse_job
from techradar.parser.main import build_gate, serve_once
from techradar.schemas.pipeline import CleanDoc, ParseJob, ParseResult

LIMITS = yaml.safe_load(Path("infra/intake/limits.yaml").read_text())
TODAY = date(2026, 11, 13)
HAVE_FFMPEG = shutil.which("ffmpeg") is not None
needs_ffmpeg = pytest.mark.skipif(not HAVE_FFMPEG, reason="ffmpeg not installed")


def test_results_carry_the_job_purpose(tmp_path):
    jobs, raw, clean = tmp_path / "jobs", tmp_path / "raw", tmp_path / "clean"
    jobs.mkdir()
    job = ParseJob(
        job_id="a" * 32,
        kind="pdf",
        raw_name="b" * 64 + ".pdf",
        url="library:1",
        source_id=0,
        origin="library",
        purpose="library",
        mode="probe",
        doc_id=1,
    )
    (jobs / f"{job.job_id}.job.json").write_text(job.model_dump_json())

    def gate(j: ParseJob) -> ParseResult:
        return ParseResult(job_id=j.job_id, kind=j.kind, status="error")  # purpose "news"

    serve_once(jobs, raw, clean, gate=gate)
    result = ParseResult.model_validate_json((clean / f"{job.job_id}.result.json").read_text())
    assert result.purpose == "library"


class FakeAv:
    def scan(self, path: Path) -> AvResult:
        return AvResult(status="clean", db_date=TODAY)


def test_library_jobs_read_from_the_originals_folder(tmp_path):
    raw, originals = tmp_path / "raw", tmp_path / "library" / "originals"
    raw.mkdir()
    originals.mkdir(parents=True)
    data = b"%PDF-1.4\n1 0 obj << >> endobj\ntrailer << >>\n%%EOF\n"
    name = hashlib.sha256(data).hexdigest() + ".pdf"
    (originals / name).write_bytes(data)
    seen = {}

    gate = build_gate(
        raw,
        tmp_path / "q",
        av=FakeAv(),
        allowed_hosts=frozenset(),
        limits=LIMITS,
        library_dir=tmp_path / "library",
    )
    import techradar.parser.main as main_mod

    def fake_run(j, raw_dir, **kw):
        seen["raw_dir"] = raw_dir
        return ParseResult(job_id=j.job_id, kind=j.kind, status="empty")

    main_mod_run = main_mod.run_with_limits
    main_mod.run_with_limits = fake_run
    try:
        job = ParseJob(
            job_id="a" * 32,
            kind="pdf",
            raw_name=name,
            url="library:1",
            source_id=0,
            origin="library",
            purpose="library",
            mode="probe",
            doc_id=1,
        )
        res = gate(job)
    finally:
        main_mod.run_with_limits = main_mod_run
    assert res.status != "error" or "raw file missing" not in str(res.intake)
    assert seen.get("raw_dir") == originals


def make_video(path: Path, seconds: int = 4) -> Path:
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


def media_job(name: str, **kw) -> ParseJob:
    return ParseJob(
        job_id="c" * 32,
        kind="video",
        raw_name=name,
        url="library:7",
        source_id=0,
        origin="library",
        purpose="library",
        doc_id=7,
        **kw,
    )


@needs_ffmpeg
def test_media_probe_reports_duration_and_streams(tmp_path):
    video = make_video(tmp_path / ("d" * 64 + ".mp4"))
    res = parse_job(media_job(video.name, mode="probe"), tmp_path, max_bytes=10**9)
    assert res.status == "ok" and res.doc is not None and res.doc.title == "probe"
    info = json.loads(res.doc.text)
    assert 3.5 < info["duration_s"] < 4.5 and info["has_audio"] and info["has_video"]


@needs_ffmpeg
def test_media_segment_writes_audio_and_slides(tmp_path, monkeypatch):
    video = make_video(tmp_path / ("e" * 64 + ".mp4"))
    monkeypatch.setattr(
        "techradar.parser.limits.offline_ocr", lambda artifacts: lambda p: "Slide " + p.stem
    )
    media_dir = tmp_path / "media"
    job = media_job(video.name, mode="media", ts_start=1.0, ts_end=3.0, part_id=2)
    res = parse_job(
        job,
        tmp_path,
        max_bytes=10**9,
        media_dir=media_dir,
        artifacts_path=tmp_path,
        frame_every_s=1,
    )
    assert res.status == "ok" and res.doc is not None and res.doc.title == "media"
    out = json.loads(res.doc.text)
    assert out["audio_file"] == "audio/seg-00001.flac"
    assert (media_dir / "7" / "audio" / "seg-00001.flac").stat().st_size > 0
    assert out["slides"] and all(1.0 <= s["ts_s"] <= 3.0 for s in out["slides"])


def test_media_segment_without_range_or_doc_is_an_error(tmp_path):
    p = tmp_path / ("f" * 64 + ".mp4")
    p.write_bytes(b"\0" * 10)
    assert (
        parse_job(media_job(p.name, mode="media"), tmp_path, media_dir=tmp_path).status == "error"
    )


def test_media_segments_with_ocr_get_room_for_the_models():
    job = media_job("f" * 64 + ".mp4", mode="media", ts_start=0.0, ts_end=600.0)
    assert address_space_for(job) == MODEL_AS_BYTES


def test_clean_doc_is_valid_for_media_json():
    CleanDoc(
        url="library:7", title="media", text='{"audio_file": "audio/seg-00000.flac"}', lang="other"
    )
