"""Phase 2c type detection: DOCX, EPUB, media and images, and size before reading."""

from datetime import date
from pathlib import Path

import pytest
import yaml

from techradar.intake.av import AvResult
from techradar.intake.filetype import check_type, detect_file_mime, detect_mime
from techradar.intake.gateway import gate_job
from techradar.schemas.pipeline import ParseJob, ParseResult

from .library_fixtures import (
    FFCONCAT,
    HLS_PLAYLIST,
    JPEG_HEAD,
    M4A_HEAD,
    MKV_HEAD,
    MOV_HEAD,
    MP3_HEAD,
    MP4_HEAD,
    OGG_HEAD,
    PNG_HEAD,
    WAV_HEAD,
    WEBM_HEAD,
    make_docx,
    make_epub,
    zip_bytes,
)

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
LIMITS = yaml.safe_load(Path("infra/intake/limits.yaml").read_text())
TODAY = date(2026, 11, 13)


def job(kind: str, ext: str, origin: str = "library") -> ParseJob:
    return ParseJob(
        job_id="a" * 32,
        kind=kind,
        raw_name="b" * 64 + "." + ext,
        url="library:x",
        source_id=0,
        origin=origin,
        purpose="library",
    )


@pytest.mark.parametrize(
    ("head", "mime"),
    [
        (MP4_HEAD, "video/mp4"),
        (MOV_HEAD, "video/quicktime"),
        (M4A_HEAD, "audio/mp4"),
        (WEBM_HEAD, "video/webm"),
        (MKV_HEAD, "video/x-matroska"),
        (MP3_HEAD, "audio/mpeg"),
        (WAV_HEAD, "audio/wav"),
        (OGG_HEAD, "audio/ogg"),
        (PNG_HEAD, "image/png"),
        (JPEG_HEAD, "image/jpeg"),
    ],
)
def test_media_and_image_signatures(head, mime):
    assert detect_mime(head) == mime


@pytest.mark.parametrize("head", [HLS_PLAYLIST, FFCONCAT])
def test_playlists_are_never_media(head):
    # A playlist or concat list named .mp4 would make ffmpeg open other
    # files; it must be refused at the type step, before ffprobe runs.
    assert not detect_mime(head).startswith(("video/", "audio/"))


def test_docx_and_epub_detected_from_the_archive(tmp_path):
    docx = make_docx(tmp_path / "a.docx")
    epub = make_epub(tmp_path / "b.epub")
    plain = tmp_path / "c.zip"
    plain.write_bytes(zip_bytes({"readme.txt": b"hi"}))
    assert detect_file_mime(docx) == DOCX_MIME
    assert detect_file_mime(epub) == "application/epub+zip"
    assert detect_file_mime(plain) == "application/zip"


def test_zip_header_allowed_only_for_docx_and_epub(tmp_path):
    docx = make_docx(tmp_path / "a.docx")
    head = docx.read_bytes()[:1024]
    assert check_type(job("docx", "docx"), DOCX_MIME, head).outcome == "ok"
    # The same ZIP header for a PDF job is still a polyglot.
    assert check_type(job("pdf", "pdf"), "application/pdf", head).outcome == "reject"


def test_mime_must_match_the_job_kind():
    assert check_type(job("video", "mp4"), "video/mp4", MP4_HEAD).outcome == "ok"
    assert check_type(job("video", "mp4"), "audio/mpeg", MP3_HEAD).outcome == "reject"
    assert check_type(job("audio", "mp3"), "audio/mpeg", MP3_HEAD).outcome == "ok"
    assert check_type(job("image", "png"), "image/png", PNG_HEAD).outcome == "ok"


class FakeAv:
    def scan(self, path: Path) -> AvResult:
        return AvResult(status="clean", db_date=TODAY)


def test_oversized_file_is_rejected_before_it_is_read(tmp_path, monkeypatch):
    # A file over its limit must never be loaded into the parser's memory.
    raw = tmp_path / "raw"
    raw.mkdir()
    f = raw / ("b" * 64 + ".pdf")
    with f.open("wb") as fh:
        fh.truncate(301_000_000)  # sparse: 301 MB on paper, nothing on disk
    real_read = Path.read_bytes

    def no_full_read(self):
        if self == f:
            raise AssertionError("oversized file was read")
        return real_read(self)

    monkeypatch.setattr(Path, "read_bytes", no_full_read)
    res = gate_job(
        job("pdf", "pdf"),
        raw,
        tmp_path / "q",
        av=FakeAv(),
        allowed_hosts=frozenset(),
        limits=LIMITS,
        parse=lambda j: ParseResult(job_id=j.job_id, kind=j.kind, status="error"),
        today=TODAY,
    )
    assert res.status == "rejected"
    assert any(s.name == "size" and s.outcome == "reject" for s in res.intake.steps)


def test_media_is_never_read_whole(tmp_path, monkeypatch):
    # A video up to 4 GB must not be loaded into memory for the byte checks.
    raw = tmp_path / "raw"
    raw.mkdir()
    f = raw / ("b" * 64 + ".mp4")
    with f.open("wb") as fh:
        fh.write(MP4_HEAD)
        fh.truncate(50_000_000)
    real_read = Path.read_bytes

    def no_full_read(self):
        if self == f:
            raise AssertionError("media file was read whole")
        return real_read(self)

    monkeypatch.setattr(Path, "read_bytes", no_full_read)
    res = gate_job(
        job("video", "mp4"),
        raw,
        tmp_path / "q",
        av=FakeAv(),
        allowed_hosts=frozenset(),
        limits=LIMITS,
        parse=lambda j: ParseResult(job_id=j.job_id, kind=j.kind, status="error"),
        today=TODAY,
    )
    # It got past the size and type checks to the structure step without the
    # file ever being read whole (no_full_read would have raised).
    assert any(s.name == "type" and s.outcome == "ok" for s in res.intake.steps)
    assert any(s.name == "structure" for s in res.intake.steps)
