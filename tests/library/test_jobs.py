"""Bulk library jobs (Phase 2c Task 4): plan, collect, chapters, resume."""

from __future__ import annotations

import json
import os
from collections.abc import AsyncGenerator
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from techradar.db.engine import make_engine
from techradar.db.models import LibraryChapter, LibraryDoc, LibraryPart
from techradar.library.jobs import (
    build_chapters,
    collect_bulk_results,
    plan_doc,
    resume_parts,
    split_full_text,
)
from techradar.pipeline.process import collect_results
from techradar.schemas.pipeline import CleanDoc, ParseJob, ParseResult
from techradar.settings import Settings

PART_PAGES = 5


def _write_result(
    clean: Path,
    job_id: str,
    status: str = "ok",
    text: str | None = "x",
    purpose: str = "library",
    kind: str = "pdf",
) -> Path:
    clean.mkdir(parents=True, exist_ok=True)
    doc = None
    if text is not None:
        doc = CleanDoc(url="library:1", title="t", text=text, lang="en")
    res = ParseResult(job_id=job_id, kind=kind, status=status, purpose=purpose, doc=doc)  # type: ignore[arg-type]
    path = clean / f"{job_id}.result.json"
    path.write_text(res.model_dump_json(), encoding="utf-8")
    return path


def _job(jobs: Path, job_id: str) -> ParseJob:
    return ParseJob.model_validate_json((jobs / f"{job_id}.job.json").read_text(encoding="utf-8"))


def _pages(first: int, last: int) -> str:
    return "\n\n".join(f"<!-- page {n} -->\ntext of page {n}" for n in range(first, last + 1))


# --- pure helpers -----------------------------------------------------------------


def test_epub_full_result_splits_on_chapter_markers():
    text = (
        "<!-- chapter 1: Start -->\nalpha\n\n<!-- chapter 2: Middle -->\nbeta\n"
        "<!-- chapter 3: End -->\ngamma"
    )
    got = split_full_text("epub", "My Book", text)
    assert [t for t, _ in got] == ["Start", "Middle", "End"]
    assert got[1][1] == "beta"  # the marker line is dropped; the title is stored separately


def test_docx_splits_on_level1_headings_and_keeps_preface():
    text = "intro line\n\n# One\nbody 1\n\n## Sub\nstill one\n\n# Two\nbody 2"
    got = split_full_text("docx", "Doc Title", text)
    assert [t for t, _ in got] == ["Doc Title", "One", "Two"]
    assert "## Sub" in got[1][1]


def test_no_headings_gives_one_chapter_titled_with_doc_title():
    assert split_full_text("html", "Page", "just words") == [("Page", "just words")]


async def test_bulk_collector_ignores_results_without_a_library_record(tmp_path: Path):
    news = _write_result(tmp_path / "clean", "a" * 32, purpose="news", kind="page")
    session = MagicMock()
    session.get = AsyncMock()
    counts = await collect_bulk_results(
        session,
        clean_dir=tmp_path / "clean",
        jobs_dir=tmp_path / "jobs",
        library_dir=tmp_path / "lib",
        part_pages=PART_PAGES,
    )
    assert news.exists() and counts["handled"] == 0
    session.get.assert_not_called()


async def test_news_collector_leaves_library_results_alone(tmp_path: Path):
    clean = tmp_path / "clean"
    lib = _write_result(clean, "b" * 32, purpose="library")
    factory = MagicMock()
    factory.return_value.__aenter__.return_value = MagicMock(commit=AsyncMock())
    deps = SimpleNamespace(session_factory=factory, clean_dir=clean)
    await collect_results(deps)  # type: ignore[arg-type]
    assert lib.exists()


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
    """A session whose changes are rolled back after the test."""
    engine = make_engine("app", db_settings)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s
        await s.rollback()
    await engine.dispose()


async def _doc(session: AsyncSession, kind: str = "pdf", status: str = "queued") -> LibraryDoc:
    sha = os.urandom(32).hex()
    ext = {"pdf": "pdf", "epub": "epub", "docx": "docx", "html": "html", "video": "mp4"}[kind]
    doc = LibraryDoc(
        sha256=sha,
        title="A Book",
        kind=kind,
        origin="library",
        original_path=f"originals/{sha}.{ext}",
        size_bytes=10,
        status=status,
        trust="open",
    )
    session.add(doc)
    await session.flush()
    return doc


class Dirs:
    def __init__(self, root: Path) -> None:
        self.jobs = root / "jobs"
        self.clean = root / "clean"
        self.lib = root / "lib"


@pytest.fixture
def dirs(tmp_path: Path) -> Dirs:
    return Dirs(tmp_path)


async def _collect(session: AsyncSession, d: Dirs) -> dict[str, int]:
    return await collect_bulk_results(
        session,
        clean_dir=d.clean,
        jobs_dir=d.jobs,
        library_dir=d.lib,
        part_pages=PART_PAGES,
        commit=False,
    )


async def _planned_with_probe(
    session: AsyncSession, d: Dirs, n_pages: int, outline: list[dict] | None = None
) -> LibraryDoc:
    doc = await _doc(session)
    [probe_id] = await plan_doc(session, doc.id, jobs_dir=d.jobs, library_dir=d.lib)
    probe = {"n_pages": n_pages, "outline": outline or []}
    _write_result(d.clean, probe_id, text=json.dumps(probe))
    await _collect(session, d)
    return doc


async def _parts(session: AsyncSession, doc_id: int) -> list[LibraryPart]:
    rows = await session.execute(
        select(LibraryPart).where(LibraryPart.doc_id == doc_id).order_by(LibraryPart.ordinal)
    )
    return list(rows.scalars())


@pytest.fixture
async def doc_with_parts(session: AsyncSession, dirs: Dirs) -> SimpleNamespace:
    """20 pages in 4 parts: parts 1-3 done, part 4 pending and its job file gone."""
    doc = await _planned_with_probe(session, dirs, 20)
    parts = await _parts(session, doc.id)
    for p in parts[:3]:
        p.status = "done"
    await session.flush()
    job4 = parts[3].job_id
    (dirs.jobs / f"{job4}.job.json").unlink()
    return SimpleNamespace(id=doc.id, part4_job_id=job4)


@pytest.mark.db
async def test_bulk_resumes_after_restart(session: AsyncSession, doc_with_parts, dirs: Dirs):
    requeued = await resume_parts(
        session, doc_with_parts.id, jobs_dir=dirs.jobs, library_dir=dirs.lib
    )
    assert requeued == [4]
    assert (dirs.jobs / f"{doc_with_parts.part4_job_id}.job.json").exists()


@pytest.mark.db
async def test_resume_skips_part_whose_result_is_waiting(
    session: AsyncSession, doc_with_parts, dirs: Dirs
):
    _write_result(dirs.clean, doc_with_parts.part4_job_id)
    got = await resume_parts(
        session, doc_with_parts.id, jobs_dir=dirs.jobs, library_dir=dirs.lib, clean_dir=dirs.clean
    )
    assert got == []


@pytest.mark.db
async def test_resume_requeues_probe_for_pdf_without_parts(session: AsyncSession, dirs: Dirs):
    doc = await _doc(session, status="processing")
    await resume_parts(session, doc.id, jobs_dir=dirs.jobs, library_dir=dirs.lib)
    [job_file] = dirs.jobs.glob("*.job.json")
    assert json.loads(job_file.read_text())["mode"] == "probe"
    # a second resume sees the probe record and does not add another job
    await resume_parts(session, doc.id, jobs_dir=dirs.jobs, library_dir=dirs.lib)
    assert len(list(dirs.jobs.glob("*.job.json"))) == 1


@pytest.mark.db
async def test_plan_doc_writes_probe_job_for_pdf(session: AsyncSession, dirs: Dirs):
    doc = await _doc(session)
    [job_id] = await plan_doc(session, doc.id, jobs_dir=dirs.jobs, library_dir=dirs.lib)
    job = _job(dirs.jobs, job_id)
    assert (job.mode, job.kind, job.purpose, job.origin) == ("probe", "pdf", "library", "library")
    assert job.url == f"library:{doc.id}" and job.source_id == 0 and job.doc_id == doc.id
    assert job.raw_name == f"{doc.sha256}.pdf"
    assert doc.status == "processing"
    assert (dirs.lib / "jobs" / f"{job_id}.json").exists()


@pytest.mark.db
@pytest.mark.parametrize(
    ("kind", "job_kind", "mode"),
    [
        ("epub", "epub", "full"),
        ("docx", "docx", "full"),
        ("html", "page", "full"),
        # Video starts with a probe; segments follow (tests/library/test_media_results.py).
        ("video", "video", "probe"),
    ],
)
async def test_plan_doc_full_and_media_jobs(
    session: AsyncSession, dirs: Dirs, kind: str, job_kind: str, mode: str
):
    doc = await _doc(session, kind=kind)
    [job_id] = await plan_doc(session, doc.id, jobs_dir=dirs.jobs, library_dir=dirs.lib)
    job = _job(dirs.jobs, job_id)
    assert (job.kind, job.mode) == (job_kind, mode)
    assert await plan_doc(session, doc.id, jobs_dir=dirs.jobs, library_dir=dirs.lib) == []


@pytest.mark.db
async def test_probe_result_creates_parts_and_part_jobs(session: AsyncSession, dirs: Dirs):
    doc = await _planned_with_probe(session, dirs, 12)
    parts = await _parts(session, doc.id)
    assert [(p.ordinal, p.page_start, p.page_end) for p in parts] == [
        (1, 1, 5),
        (2, 6, 10),
        (3, 11, 12),
    ]
    assert all(p.status == "pending" and p.job_id for p in parts)
    job = _job(dirs.jobs, parts[1].job_id)
    assert (job.mode, job.page_start, job.page_end, job.part_id) == ("part", 6, 10, parts[1].id)
    assert doc.pages == 12
    assert (dirs.lib / "text" / str(doc.id) / "probe.json").exists()
    assert not list(dirs.clean.glob("*.result.json"))  # consumed


@pytest.mark.db
async def test_collecting_the_same_probe_twice_does_not_duplicate_parts(
    session: AsyncSession, dirs: Dirs
):
    doc = await _doc(session)
    [probe_id] = await plan_doc(session, doc.id, jobs_dir=dirs.jobs, library_dir=dirs.lib)
    result = _write_result(dirs.clean, probe_id, text=json.dumps({"n_pages": 12, "outline": []}))
    saved = result.read_text()
    await _collect(session, dirs)
    result.write_text(saved)  # crash before delete: the same result shows up again
    (dirs.lib / "jobs" / f"{probe_id}.json").write_text(
        json.dumps({"doc_id": doc.id, "kind": "probe", "part_id": None})
    )
    await _collect(session, dirs)
    assert len(await _parts(session, doc.id)) == 3


@pytest.mark.db
async def test_part_result_saved_and_part_done(session: AsyncSession, dirs: Dirs):
    doc = await _planned_with_probe(session, dirs, 12)
    p1 = (await _parts(session, doc.id))[0]
    _write_result(dirs.clean, p1.job_id, text=_pages(1, 5))
    await _collect(session, dirs)
    assert p1.status == "done"
    assert p1.result_path == f"text/{doc.id}/parts/1.md"
    assert "text of page 3" in (dirs.lib / p1.result_path).read_text()


@pytest.mark.db
async def test_failed_part_retried_then_failed_after_three_attempts(
    session: AsyncSession, dirs: Dirs
):
    doc = await _planned_with_probe(session, dirs, 5)
    [part] = await _parts(session, doc.id)
    seen = {part.job_id}
    for attempt in (1, 2):
        _write_result(dirs.clean, part.job_id, status="error", text=None)
        await _collect(session, dirs)
        assert part.status == "pending" and part.attempts == attempt
        assert part.job_id not in seen
        seen.add(part.job_id)
        assert (dirs.jobs / f"{part.job_id}.job.json").exists()
    _write_result(dirs.clean, part.job_id, status="too_large", text=None)
    await _collect(session, dirs)
    assert part.status == "failed" and part.attempts == 3


@pytest.mark.db
async def test_all_parts_done_builds_chapters_with_missing_pages(session: AsyncSession, dirs: Dirs):
    outline = [
        {"title": "One", "page": 1, "level": 1},
        {"title": "Two", "page": 6, "level": 1},
    ]
    doc = await _planned_with_probe(session, dirs, 10, outline)
    p1, p2 = await _parts(session, doc.id)
    _write_result(dirs.clean, p1.job_id, text=_pages(1, 5))
    await _collect(session, dirs)
    assert (await session.get(LibraryDoc, doc.id)).status == "processing"
    for _ in range(3):
        _write_result(dirs.clean, p2.job_id, status="error", text=None)
        await _collect(session, dirs)
    assert p2.status == "failed"
    rows = (
        (
            await session.execute(
                select(LibraryChapter)
                .where(LibraryChapter.doc_id == doc.id)
                .order_by(LibraryChapter.ordinal)
            )
        )
        .scalars()
        .all()
    )
    assert [(c.title, c.page_start, c.page_end) for c in rows] == [("One", 1, 5), ("Two", 6, 10)]
    assert rows[0].missing_pages == [] and rows[1].missing_pages == [6, 7, 8, 9, 10]
    assert "text of page 2" in (dirs.lib / rows[0].text_path).read_text()
    assert "couldn't be read" in (dirs.lib / rows[1].text_path).read_text()
    assert doc.status == "processing"  # Task 6 sets `ready`


@pytest.mark.db
async def test_build_chapters_uses_headings_in_part_text(session: AsyncSession, dirs: Dirs):
    doc = await _planned_with_probe(session, dirs, 10)
    p1, p2 = await _parts(session, doc.id)
    _write_result(
        dirs.clean,
        p1.job_id,
        text=_pages(1, 2) + "\n\n<!-- page 3 -->\n# Intro\nx\n" + _pages(4, 5),
    )
    _write_result(
        dirs.clean,
        p2.job_id,
        text=_pages(6, 7) + "\n\n<!-- page 8 -->\n# Next\ny\n" + _pages(9, 10),
    )
    await _collect(session, dirs)
    await build_chapters(session, doc.id, library_dir=dirs.lib, part_pages=PART_PAGES)  # idempotent
    rows = (
        (await session.execute(select(LibraryChapter).where(LibraryChapter.doc_id == doc.id)))
        .scalars()
        .all()
    )
    assert sorted((c.title, c.page_start, c.page_end) for c in rows) == [
        ("Intro", 1, 7),
        ("Next", 8, 10),
    ]


@pytest.mark.db
async def test_quarantined_result_marks_doc_and_writes_no_more_jobs(
    session: AsyncSession, dirs: Dirs
):
    doc = await _planned_with_probe(session, dirs, 12)
    parts = await _parts(session, doc.id)
    _write_result(dirs.clean, parts[0].job_id, status="quarantined", text=None)
    await _collect(session, dirs)
    assert (await session.get(LibraryDoc, doc.id)).status == "quarantined"
    assert not list(dirs.jobs.glob("*.job.json"))  # pending part jobs withdrawn
    # a straggler result of the same doc changes nothing and creates no job
    _write_result(dirs.clean, parts[1].job_id, text=_pages(6, 10))
    await _collect(session, dirs)
    assert parts[1].status == "pending" and not list(dirs.jobs.glob("*.job.json"))
    assert (await session.get(LibraryDoc, doc.id)).status == "quarantined"


@pytest.mark.db
async def test_epub_full_result_builds_chapters(session: AsyncSession, dirs: Dirs):
    doc = await _doc(session, kind="epub")
    [job_id] = await plan_doc(session, doc.id, jobs_dir=dirs.jobs, library_dir=dirs.lib)
    _write_result(
        dirs.clean,
        job_id,
        kind="epub",
        text="<!-- chapter 1: Start -->\nalpha\n<!-- chapter 2: End -->\nbeta",
    )
    await _collect(session, dirs)
    rows = (
        (
            await session.execute(
                select(LibraryChapter)
                .where(LibraryChapter.doc_id == doc.id)
                .order_by(LibraryChapter.ordinal)
            )
        )
        .scalars()
        .all()
    )
    assert [c.title for c in rows] == ["Start", "End"]
    assert rows[0].page_start is None and rows[0].text_path == f"text/{doc.id}/01.md"
    assert doc.status == "processing"
