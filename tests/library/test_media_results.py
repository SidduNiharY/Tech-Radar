"""Media job result: strict validation and library handling (Phase 2c Task 5)."""

from __future__ import annotations

import json
import os
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from techradar.db.engine import make_engine
from techradar.db.models import LibraryDoc, LibraryPart, Outbox
from techradar.library.jobs import JobRecord, _write_record, collect_bulk_results, plan_doc
from techradar.library.media_results import (
    parse_probe,
    parse_segment_result,
    segment_bounds,
)
from techradar.schemas.pipeline import CleanDoc, ParseResult
from techradar.settings import Settings


def _seg(file: str = "audio/seg-00600.flac", slides: list | None = None) -> str:
    return json.dumps({"audio_file": file, "slides": slides or [{"ts_s": 650.0, "text": "hi"}]})


# --- pure validators --------------------------------------------------------------


def test_segment_bounds_cover_duration():
    assert segment_bounds(1300.0) == [(0.0, 600.0), (600.0, 1200.0), (1200.0, 1300.0)]
    assert segment_bounds(600.0) == [(0.0, 600.0)]


def test_valid_segment_accepted():
    assert parse_segment_result(_seg(), 600.0, 1200.0) is not None


@pytest.mark.parametrize(
    "text",
    [
        _seg("../x"),
        _seg("audio/seg-1.flac"),
        _seg("audio/seg-00000.flac"),  # right shape, wrong segment
        _seg("audio/seg-00600.flac\n"),
        _seg("/etc/passwd"),
        _seg(slides=[{"ts_s": 1200.5, "text": "late"}]),
        _seg(slides=[{"ts_s": 599.0, "text": "early"}]),
        _seg(slides=[{"ts_s": 700.0, "text": "x" * 4001}]),
        _seg(slides=[{"ts_s": 700.0, "text": "x"}] * 41),
        '{"audio_file": "audio/seg-00600.flac"}',
        "not json",
        "[]",
        "",
    ],
)
def test_bad_segments_rejected(text: str):
    assert parse_segment_result(text, 600.0, 1200.0) is None


@pytest.mark.parametrize(
    "text",
    [
        '{"duration_s": 0, "has_audio": true, "has_video": true}',
        '{"duration_s": 14461, "has_audio": true, "has_video": true}',
        '{"duration_s": -3, "has_audio": true, "has_video": true}',
        '{"duration_s": 10}',
        "nope",
    ],
)
def test_bad_probes_rejected(text: str):
    assert parse_probe(text) is None


def test_good_probe_accepted():
    assert parse_probe('{"duration_s": 14460, "has_audio": true, "has_video": false}')


# --- database tests ---------------------------------------------------------------


@pytest.fixture
def db_settings() -> Settings:
    return Settings(
        telegram_owner_chat_id=1,
        db_host="127.0.0.1",
        db_port=55432,
        db_name="techradar",
        secrets_dir=Path("secrets"),
    )


@pytest.fixture
async def session(db_settings: Settings) -> AsyncGenerator[AsyncSession]:
    engine = make_engine("app", db_settings)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s
        await s.rollback()
    await engine.dispose()


class Dirs:
    def __init__(self, root: Path) -> None:
        self.jobs = root / "jobs"
        self.clean = root / "clean"
        self.lib = root / "lib"


@pytest.fixture
def dirs(tmp_path: Path) -> Dirs:
    return Dirs(tmp_path)


@pytest.fixture
def library_dir(dirs: Dirs) -> Path:
    return dirs.lib


async def _media_doc(session: AsyncSession, d: Dirs, kind: str, keep: bool) -> LibraryDoc:
    sha = os.urandom(32).hex()
    rel = f"originals/{sha}.{'mp4' if kind == 'video' else 'mp3'}"
    (d.lib / "originals").mkdir(parents=True, exist_ok=True)
    (d.lib / rel).write_bytes(b"media")
    doc = LibraryDoc(
        sha256=sha, title="Lecture 1", kind=kind, origin="library", original_path=rel,
        size_bytes=5, status="queued", trust="open", keep_media=keep,
    )  # fmt: skip
    session.add(doc)
    await session.flush()
    return doc


def _result(d: Dirs, job_id: str, status: str, title: str, text: str | None) -> None:
    d.clean.mkdir(parents=True, exist_ok=True)
    doc = CleanDoc(url="library:1", title=title, text=text, lang="en") if text else None
    res = ParseResult(job_id=job_id, kind="video", status=status, purpose="library", doc=doc)  # type: ignore[arg-type]
    (d.clean / f"{job_id}.result.json").write_text(res.model_dump_json(), encoding="utf-8")


async def _collect(session: AsyncSession, d: Dirs) -> dict[str, int]:
    return await collect_bulk_results(
        session, clean_dir=d.clean, jobs_dir=d.jobs, library_dir=d.lib, part_pages=5,
        commit=False, owner_chat_id=1,
    )  # fmt: skip


async def _parts(session: AsyncSession, doc_id: int) -> list[LibraryPart]:
    rows = await session.execute(
        select(LibraryPart).where(LibraryPart.doc_id == doc_id).order_by(LibraryPart.ordinal)
    )
    return list(rows.scalars())


def _seg_ok(part: LibraryPart) -> str:
    name = f"audio/seg-{int(part.ts_start or 0):05d}.flac"
    return json.dumps({"audio_file": name, "slides": [{"ts_s": part.ts_start, "text": "s"}]})


async def _probed(session: AsyncSession, d: Dirs, kind: str, keep: bool) -> LibraryDoc:
    doc = await _media_doc(session, d, kind, keep)
    [job_id] = await plan_doc(session, doc.id, jobs_dir=d.jobs, library_dir=d.lib, commit=False)
    probe = {"duration_s": 1300.0, "has_audio": True, "has_video": kind == "video"}
    _result(d, job_id, "ok", "probe", json.dumps(probe))
    await _collect(session, d)
    return doc


def _audio(d: Dirs, doc_id: int, part: LibraryPart) -> None:
    """The parser's audio file for a segment (the collector checks it exists)."""
    path = d.lib / "media" / str(doc_id) / f"audio/seg-{int(part.ts_start or 0):05d}.flac"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"fLaC audio")


async def _finish_all(session: AsyncSession, d: Dirs, doc: LibraryDoc) -> None:
    for p in await _parts(session, doc.id):
        _audio(d, doc.id, p)
        _result(d, p.job_id or "", "ok", "media", _seg_ok(p))
    await _collect(session, d)
    await session.refresh(doc)


@pytest.fixture
def media_result(session: AsyncSession, dirs: Dirs):
    """Plan a media doc, run its probe and answer every segment job; returns the doc."""

    async def make(kind: str = "video", keep: bool = False) -> LibraryDoc:
        doc = await _probed(session, dirs, kind, keep)
        await _finish_all(session, dirs, doc)
        return doc

    return make


async def _messages(session: AsyncSession, doc_id: int) -> list[Outbox]:
    rows = await session.execute(
        select(Outbox).where(Outbox.purpose == "library_ready", Outbox.ref_id == doc_id)
    )
    return list(rows.scalars())


@pytest.mark.db
async def test_media_probe_plans_one_job_per_segment(session, dirs):
    doc = await _probed(session, dirs, "video", False)
    parts = await _parts(session, doc.id)
    assert [(p.ts_start, p.ts_end, p.status) for p in parts] == [
        (0.0, 600.0, "pending"),
        (600.0, 1200.0, "pending"),
        (1200.0, 1300.0, "pending"),
    ]
    job = json.loads((dirs.jobs / f"{parts[1].job_id}.job.json").read_text())
    assert job["mode"] == "media" and job["ts_start"] == 600.0 and job["part_id"] == parts[1].id
    assert doc.duration_s == 1300.0 and doc.status == "processing"


@pytest.mark.db
async def test_media_result_awaits_transcription(session, media_result, dirs):
    doc = await media_result()
    assert doc.status == "awaiting_transcription"
    parts = await _parts(session, doc.id)
    assert [(p.ordinal, p.ts_start, p.ts_end, p.status) for p in parts] == [
        (0, 0.0, 600.0, "done"),
        (1, 600.0, 1200.0, "done"),
        (2, 1200.0, 1300.0, "done"),
    ]
    assert parts[1].result_path == f"media/{doc.id}/audio/seg-00600.flac"
    slides = json.loads((dirs.lib / "text" / str(doc.id) / "slides.json").read_text())
    assert [s["ts_s"] for s in slides] == [0.0, 600.0, 1200.0]


@pytest.mark.db
async def test_video_deleted_unless_kept(session, media_result, library_dir):
    doc = await media_result()
    assert not (library_dir / doc.original_path).exists()
    kept = await media_result(keep=True)
    assert (library_dir / kept.original_path).exists()
    audio = await media_result(kind="audio")
    assert (library_dir / audio.original_path).exists()


@pytest.mark.db
async def test_symlinked_original_is_not_followed(session, dirs, tmp_path):
    doc = await _probed(session, dirs, "video", False)
    target = tmp_path / "precious"
    target.write_bytes(b"keep me")
    path = dirs.lib / doc.original_path
    path.unlink()
    path.symlink_to(target)
    await _finish_all(session, dirs, doc)
    assert doc.status == "awaiting_transcription" and target.read_bytes() == b"keep me"


@pytest.mark.db
async def test_ready_message_sent_once_even_if_collected_twice(session, dirs):
    doc = await _probed(session, dirs, "video", False)
    parts = await _parts(session, doc.id)
    await _finish_all(session, dirs, doc)
    for p in parts:  # a straggler: record and result reappear
        _write_record(
            dirs.lib, p.job_id or "", JobRecord(doc_id=doc.id, kind="media", part_id=p.id)
        )
        _result(dirs, p.job_id or "", "ok", "media", _seg_ok(p))
    await _collect(session, dirs)
    [msg] = await _messages(session, doc.id)
    assert msg.text == (
        "Got Lecture 1: audio and slides are ready; the transcript comes when phase 6 is built."
    )


@pytest.mark.db
async def test_bad_segment_retries_then_fails_that_part(session, dirs):
    doc = await _probed(session, dirs, "video", False)
    first = (await _parts(session, doc.id))[0]
    for attempt in range(3):
        part = (await _parts(session, doc.id))[0]
        _result(dirs, part.job_id or "", "ok", "media", _seg("../evil"))
        await _collect(session, dirs)
        await session.refresh(part)
        assert part.attempts == attempt + 1
    assert part.status == "failed" and first.id == part.id


@pytest.mark.db
async def test_all_segments_failed_fails_doc(session, dirs):
    doc = await _probed(session, dirs, "video", True)
    for _ in range(3):
        for p in await _parts(session, doc.id):
            if p.status == "pending":
                _result(dirs, p.job_id or "", "error", "media", None)
        await _collect(session, dirs)
    await session.refresh(doc)
    assert doc.status == "failed" and not await _messages(session, doc.id)


@pytest.mark.db
async def test_probe_without_streams_fails_doc(session, dirs):
    doc = await _media_doc(session, dirs, "video", False)
    [job_id] = await plan_doc(
        session, doc.id, jobs_dir=dirs.jobs, library_dir=dirs.lib, commit=False
    )
    _result(
        dirs, job_id, "ok", "probe", '{"duration_s": 5, "has_audio": false, "has_video": false}'
    )
    await _collect(session, dirs)
    await session.refresh(doc)
    assert doc.status == "failed"


@pytest.mark.db
async def test_silent_video_fails_the_doc_and_tells_the_owner(session, dirs):
    doc = await _media_doc(session, dirs, "video", False)
    [job_id] = await plan_doc(
        session, doc.id, jobs_dir=dirs.jobs, library_dir=dirs.lib, commit=False
    )
    _result(
        dirs, job_id, "ok", "probe", '{"duration_s": 60, "has_audio": false, "has_video": true}'
    )
    await _collect(session, dirs)
    await session.refresh(doc)
    assert doc.status == "failed" and await _parts(session, doc.id) == []
    rows = await session.execute(
        select(Outbox).where(Outbox.purpose == "library_failed", Outbox.ref_id == doc.id)
    )
    assert len(list(rows.scalars())) == 1
