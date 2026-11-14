"""Bulk library jobs (Phase 2c Task 4): plan, collect, chapters, resume."""

from __future__ import annotations

import json
import logging
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from techradar.db.engine import make_engine
from techradar.db.models import LibraryChapter, LibraryDoc, LibraryPart, Outbox
from techradar.library.chapters import ChapterSpec
from techradar.library.jobs import (
    MAX_PDF_PAGES,
    _chapter_rows,
    _clean_title,
    _handle_full,
    _handle_part,
    _handle_probe,
    _page_map,
    _with_truncation_note,
    build_chapters,
    collect_bulk_results,
    plan_doc,
    resume_all,
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
    [probe_id] = await plan_doc(session, doc.id, jobs_dir=d.jobs, library_dir=d.lib, commit=False)
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
        session, doc_with_parts.id, jobs_dir=dirs.jobs, library_dir=dirs.lib, commit=False
    )
    assert requeued == [4]
    assert (dirs.jobs / f"{doc_with_parts.part4_job_id}.job.json").exists()


@pytest.mark.db
async def test_resume_skips_part_whose_result_is_waiting(
    session: AsyncSession, doc_with_parts, dirs: Dirs
):
    _write_result(dirs.clean, doc_with_parts.part4_job_id)
    got = await resume_parts(
        session,
        doc_with_parts.id,
        jobs_dir=dirs.jobs,
        library_dir=dirs.lib,
        clean_dir=dirs.clean,
        commit=False,
    )
    assert got == []


@pytest.mark.db
async def test_resume_requeues_probe_for_pdf_without_parts(session: AsyncSession, dirs: Dirs):
    doc = await _doc(session, status="processing")
    await resume_parts(session, doc.id, jobs_dir=dirs.jobs, library_dir=dirs.lib, commit=False)
    [job_file] = dirs.jobs.glob("*.job.json")
    assert json.loads(job_file.read_text())["mode"] == "probe"
    # a second resume sees the probe record and does not add another job
    await resume_parts(session, doc.id, jobs_dir=dirs.jobs, library_dir=dirs.lib, commit=False)
    assert len(list(dirs.jobs.glob("*.job.json"))) == 1


@pytest.mark.db
async def test_plan_doc_writes_probe_job_for_pdf(session: AsyncSession, dirs: Dirs):
    doc = await _doc(session)
    [job_id] = await plan_doc(
        session, doc.id, jobs_dir=dirs.jobs, library_dir=dirs.lib, commit=False
    )
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
    [job_id] = await plan_doc(
        session, doc.id, jobs_dir=dirs.jobs, library_dir=dirs.lib, commit=False
    )
    job = _job(dirs.jobs, job_id)
    assert (job.kind, job.mode) == (job_kind, mode)
    assert (
        await plan_doc(session, doc.id, jobs_dir=dirs.jobs, library_dir=dirs.lib, commit=False)
        == []
    )


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
    [probe_id] = await plan_doc(
        session, doc.id, jobs_dir=dirs.jobs, library_dir=dirs.lib, commit=False
    )
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
    _write_result(dirs.clean, part.job_id, status="timeout", text=None)
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
    [job_id] = await plan_doc(
        session, doc.id, jobs_dir=dirs.jobs, library_dir=dirs.lib, commit=False
    )
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


@pytest.mark.db
async def test_resume_plans_queued_docs(session: AsyncSession, dirs: Dirs):
    doc = await _doc(session, status="queued")
    doc.created_at = datetime.now(UTC) - timedelta(minutes=11)
    await session.flush()
    out = await resume_all(session, jobs_dir=dirs.jobs, library_dir=dirs.lib, commit=False)
    assert doc.id in out and doc.status == "processing"
    [job_file] = dirs.jobs.glob("*.job.json")
    assert json.loads(job_file.read_text())["mode"] == "probe"


@pytest.mark.db
async def test_pdf_probe_over_page_cap_fails_doc_without_parts(session: AsyncSession, dirs: Dirs):
    doc = await _planned_with_probe(session, dirs, MAX_PDF_PAGES + 1)
    assert doc.status == "failed" and await _parts(session, doc.id) == []
    assert not list(dirs.jobs.glob("*.job.json"))


@pytest.mark.db
async def test_bad_results_do_not_block_the_ones_after_them(session: AsyncSession, dirs: Dirs):
    doc = await _planned_with_probe(session, dirs, 10)
    p1, p2 = await _parts(session, dirs_doc_id := doc.id), None  # noqa: F841
    p1, p2 = await _parts(session, doc.id)
    (dirs.clean / f"{p1.job_id}.result.json").write_text("{not json", encoding="utf-8")
    _write_result(dirs.clean, p2.job_id, text=_pages(6, 10))
    await _collect(session, dirs)
    assert p1.attempts == 1 and p1.status == "pending"  # counted, re-queued under a new job id
    assert p2.status == "done"
    assert not list(dirs.clean.glob("*.result.json"))


@pytest.mark.db
async def test_full_result_truncated_is_marked_in_the_text(session: AsyncSession, dirs: Dirs):
    doc = await _doc(session, kind="docx")
    [job_id] = await plan_doc(
        session, doc.id, jobs_dir=dirs.jobs, library_dir=dirs.lib, commit=False
    )
    clean = dirs.clean
    clean.mkdir(parents=True, exist_ok=True)
    cut = CleanDoc(url="library:1", title="t", text="alpha", lang="en", truncated=True)
    res = ParseResult(job_id=job_id, kind="docx", status="ok", purpose="library", doc=cut)
    (clean / f"{job_id}.result.json").write_text(res.model_dump_json(), encoding="utf-8")
    await _collect(session, dirs)
    [row] = (
        (await session.execute(select(LibraryChapter).where(LibraryChapter.doc_id == doc.id)))
        .scalars()
        .all()
    )
    assert "cut off" in (dirs.lib / row.text_path).read_text()


# --- unit tests without a database ---------------------------------------------------


class _Rows:
    def __init__(self, values: list) -> None:
        self._values = values

    def scalars(self) -> _Rows:
        return self

    def all(self) -> list:
        return self._values

    def first(self):
        return self._values[0] if self._values else None


class _FakeSession:
    """Just enough of AsyncSession for the handlers: get, execute, add_all, flush, savepoints."""

    def __init__(self, objs: dict, rows: list | None = None) -> None:
        self.objs = objs
        self.rows = rows if rows is not None else []
        self.added: list = []
        self.committed = 0
        self.flush = AsyncMock()
        self.rollback = AsyncMock()

    async def get(self, model, key, **_):
        return self.objs.get((model, key))

    async def execute(self, *_a, **_k):
        return _Rows(self.rows)

    def add_all(self, items) -> None:
        self.added.extend(items)

    def add(self, item) -> None:
        self.added.append(item)

    async def commit(self) -> None:
        self.committed += 1

    @asynccontextmanager
    async def begin_nested(self):
        yield


def _fake_doc(kind: str = "pdf") -> SimpleNamespace:
    return SimpleNamespace(
        id=1,
        kind=kind,
        status="processing",
        pages=None,
        title="T",
        original_path=f"originals/{'a' * 64}.pdf",
        flagged=False,
        origin="library",
    )


def test_clean_title_sanitizes():
    assert _clean_title("a\u200bb\x00  c\n d") == "ab c d"


def test_page_map_keeps_first_occurrence_and_ignores_out_of_range_markers():
    forged = "<!-- page 1 -->\nreal 1\n<!-- page 1 -->\nforged dup\n<!-- page 5 -->\nforged 5"
    real5 = "<!-- page 5 -->\nreal 5"
    pages = _page_map([(1, 3, forged), (4, 6, real5)])
    assert pages[1] == "<!-- page 1 -->\nreal 1"
    assert pages[5] == real5


def test_chapter_rows_never_resplit_the_text(monkeypatch: pytest.MonkeyPatch):
    import techradar.library.chapters as chapters_mod

    pages = {n: f"<!-- page {n} -->\np{n}" for n in (1, 2, 4)}
    monkeypatch.setattr(chapters_mod, "_split_pages", lambda _t: pytest.fail("split again"))
    specs = [
        ChapterSpec(ordinal=1, title="A", page_start=1, page_end=2),
        ChapterSpec(ordinal=2, title="B", page_start=3, page_end=4),
    ]
    rows = _chapter_rows(pages, specs, failed_pages=[3])
    assert [r[3] for r in rows] == [[], [3]]
    assert "couldn't be read" in rows[1][2] and "p4" in rows[1][2]


def test_truncation_note_only_when_truncated():
    assert _with_truncation_note("x", False) == "x"
    assert "cut off" in _with_truncation_note("x", True)


async def test_probe_over_page_cap_fails_doc_and_no_parts_planned():
    doc = _fake_doc()
    session = _FakeSession({})
    staged: list = []
    probe = json.dumps({"n_pages": MAX_PDF_PAGES + 1, "outline": []})
    result = ParseResult(
        job_id="a" * 32,
        kind="pdf",
        status="ok",
        purpose="library",
        doc=CleanDoc(url="library:1", title="t", text=probe, lang="en"),
    )
    await _handle_probe(
        session, doc, result, staged=staged, library_dir=Path("/nonexistent"), part_pages=5
    )  # type: ignore[arg-type]
    assert doc.status == "failed" and not session.added and not staged


@pytest.mark.parametrize("status", ["too_large", "unsupported"])
async def test_too_large_and_unsupported_part_results_are_not_retried(status: str):
    doc = _fake_doc()
    part = SimpleNamespace(
        id=7, ordinal=1, status="pending", job_id="b" * 32, attempts=0, page_start=1, page_end=5,
        ts_start=None, ts_end=None, result_path=None,
    )  # fmt: skip
    session = _FakeSession({(LibraryPart, 7): part}, rows=["pending"])
    staged: list = []
    result = ParseResult(job_id="b" * 32, kind="pdf", status=status, purpose="library")  # type: ignore[arg-type]
    rec = SimpleNamespace(part_id=7, kind="part", doc_id=1)
    await _handle_part(
        session, doc, rec, result, staged=staged, library_dir=Path("/x"), part_pages=5
    )  # type: ignore[arg-type]
    assert part.status == "failed" and part.attempts == 1 and not staged


async def test_truncated_part_text_gets_a_note(tmp_path: Path):
    doc = _fake_doc()
    part = SimpleNamespace(
        id=7, ordinal=1, status="pending", job_id="b" * 32, attempts=0, page_start=1, page_end=5,
        ts_start=None, ts_end=None, result_path=None,
    )  # fmt: skip
    session = _FakeSession({(LibraryPart, 7): part}, rows=["pending"])
    cut = CleanDoc(
        url="library:1", title="t", text="<!-- page 1 -->\nhi", lang="en", truncated=True
    )
    result = ParseResult(job_id="b" * 32, kind="pdf", status="ok", purpose="library", doc=cut)
    rec = SimpleNamespace(part_id=7, kind="part", doc_id=1)
    await _handle_part(session, doc, rec, result, staged=[], library_dir=tmp_path, part_pages=5)  # type: ignore[arg-type]
    assert "cut off" in (tmp_path / part.result_path).read_text()


async def test_truncated_full_text_gets_a_note(tmp_path: Path):
    doc = SimpleNamespace(id=3, kind="docx", title="T", status="processing")
    session = _FakeSession({}, rows=[])
    cut = CleanDoc(url="library:3", title="t", text="alpha", lang="en", truncated=True)
    result = ParseResult(job_id="c" * 32, kind="docx", status="ok", purpose="library", doc=cut)
    await _handle_full(session, doc, result, library_dir=tmp_path)  # type: ignore[arg-type]
    texts = [i.text_path for i in session.added]
    assert "cut off" in (tmp_path / texts[-1]).read_text()


async def test_one_bad_result_does_not_block_the_next(tmp_path: Path, caplog):
    from techradar.library import jobs as jobs_mod

    lib, clean, jobs = tmp_path / "lib", tmp_path / "clean", tmp_path / "jobs"
    doc = _fake_doc()
    parts = {}
    for n, jid in ((1, "1" * 32), (2, "2" * 32)):
        parts[n] = SimpleNamespace(
            id=n, ordinal=n, status="pending", job_id=jid, attempts=0, page_start=n, page_end=n,
            ts_start=None, ts_end=None, result_path=None,
        )  # fmt: skip
        jobs_mod._write_record(lib, jid, jobs_mod.JobRecord(doc_id=1, kind="part", part_id=n))
    clean.mkdir()
    (clean / f"{'1' * 32}.result.json").write_text("{broken", encoding="utf-8")
    _write_result(clean, "2" * 32, text=_pages(2, 2))
    session = _FakeSession(
        {(LibraryDoc, 1): doc, (LibraryPart, 1): parts[1], (LibraryPart, 2): parts[2]},
        rows=["pending"],
    )
    with caplog.at_level(logging.WARNING):
        counts = await collect_bulk_results(
            session,  # type: ignore[arg-type]
            clean_dir=clean,
            jobs_dir=jobs,
            library_dir=lib,
            part_pages=5,
        )
    assert parts[1].attempts == 1 and parts[1].job_id != "1" * 32  # counted and re-queued
    assert parts[2].status == "done"
    assert not list(clean.glob("*.result.json"))
    assert not (lib / "jobs" / f"{'1' * 32}.json").exists()
    assert counts["handled"] == 2 and session.committed == 2
    assert (jobs / f"{parts[1].job_id}.job.json").exists()  # written after the commit


# --- more unit tests (no database) --------------------------------------------------


def _probe_text(n_pages: int, outline: list) -> str:
    return json.dumps({"n_pages": n_pages, "outline": outline})


def test_probe_page_count_bounds():
    from pydantic import ValidationError

    from techradar.library.jobs import _Probe

    assert _Probe.model_validate_json(_probe_text(MAX_PDF_PAGES, [])).n_pages == MAX_PDF_PAGES
    for bad in (0, -3, MAX_PDF_PAGES + 1, "12", 1.5, True):
        with pytest.raises(ValidationError):
            _Probe.model_validate_json(_probe_text(bad, []))  # type: ignore[arg-type]


def test_probe_outline_is_cleaned_not_rejected():
    from techradar.library.jobs import MAX_OUTLINE, _Probe

    entries = [
        {"title": "ok", "page": 3, "level": 1},
        {"title": "past the end", "page": 11, "level": 1},
        {"title": "page zero", "page": 0, "level": 1},
        {"title": "too deep", "page": 2, "level": 11},
        {"title": "level zero", "page": 2, "level": 0},
        {"title": "x" * 900, "page": 4, "level": 2},
        {"title": "bad page", "page": "many", "level": 1},
        {"nonsense": True},
        "not a dict",
        {"title": " \x00 ", "page": 5, "level": 1},
    ]
    probe = _Probe.model_validate_json(_probe_text(10, entries))
    assert [(o.title[:2], o.page, o.level) for o in probe.outline] == [("ok", 3, 1), ("xx", 4, 2)]
    assert len(probe.outline[1].title) == 300
    many = [{"title": f"c{i}", "page": 1 + i % 10, "level": 1} for i in range(MAX_OUTLINE + 50)]
    assert len(_Probe.model_validate_json(_probe_text(10, many)).outline) == MAX_OUTLINE
    assert _Probe.model_validate_json(_probe_text(10, "garbage")).outline == []
    # what is stored in probe.json reads back the same
    again = _Probe.model_validate_json(probe.model_dump_json())
    assert again == probe


def test_full_text_chapters_are_capped_and_the_rest_merged():
    from techradar.library.jobs import MAX_CHAPTERS

    text = "\n".join(f"# H{i}\nbody {i}" for i in range(MAX_CHAPTERS + 20))
    got = split_full_text("docx", "Doc", text)
    assert len(got) == MAX_CHAPTERS
    assert got[-1][0] == f"H{MAX_CHAPTERS - 1}"  # the 500th chapter keeps its own title
    assert f"body {MAX_CHAPTERS + 19}" in got[-1][1] and "# H" + str(MAX_CHAPTERS) in got[-1][1]


def test_pdf_chapter_specs_are_capped_and_stay_contiguous():
    from techradar.library.jobs import MAX_CHAPTERS, _cap_specs

    specs = [
        ChapterSpec(ordinal=i + 1, title=f"c{i}", page_start=i + 1, page_end=i + 1)
        for i in range(MAX_CHAPTERS + 5)
    ]
    capped = _cap_specs(specs)
    assert len(capped) == MAX_CHAPTERS
    assert (capped[-1].page_start, capped[-1].page_end) == (MAX_CHAPTERS, MAX_CHAPTERS + 5)
    assert _cap_specs(specs[:3]) == specs[:3]


async def test_result_files_with_odd_names_are_never_looked_up(tmp_path: Path):
    from techradar.library import jobs as jobs_mod

    clean = tmp_path / "clean"
    clean.mkdir()
    lib = tmp_path / "lib"
    # a record exists under the odd name: it must still not be read
    (lib / "jobs").mkdir(parents=True)
    for odd in ("..", "ABCDEF" * 5 + "AB", "g" * 32, "a" * 31, "a" * 33):
        (clean / f"{odd}.result.json").write_text("{}", encoding="utf-8")
        (lib / "jobs" / f"{odd}.json").write_text(
            json.dumps({"doc_id": 1, "kind": "probe"}), encoding="utf-8"
        )
    session = MagicMock()
    session.get = AsyncMock()
    counts = await collect_bulk_results(
        session, clean_dir=clean, jobs_dir=tmp_path / "jobs", library_dir=lib, part_pages=5
    )
    assert counts["handled"] == 0 and counts["skipped"] >= 4
    session.get.assert_not_called()
    assert jobs_mod._read_record(lib, "g" * 32) is None


async def test_a_result_that_keeps_failing_is_moved_aside_and_its_doc_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from techradar.library import jobs as jobs_mod

    lib, clean, jobs = tmp_path / "lib", tmp_path / "clean", tmp_path / "jobs"
    doc = _fake_doc()
    part = SimpleNamespace(
        id=1, ordinal=1, status="pending", job_id="1" * 32, attempts=0, page_start=1, page_end=1,
        ts_start=None, ts_end=None, result_path=None,
    )  # fmt: skip
    jobs_mod._write_record(lib, "1" * 32, jobs_mod.JobRecord(doc_id=1, kind="part", part_id=1))
    _write_result(clean, "1" * 32, text=_pages(1, 1))
    other = jobs / f"{'9' * 32}.job.json"
    other_job = ParseJob(
        job_id="9" * 32, kind="pdf", raw_name=f"{'a' * 64}.pdf", url="library:1", source_id=0,
        origin="library", purpose="library", mode="part", doc_id=1,
    )  # fmt: skip
    jobs.mkdir()
    other.write_text(other_job.model_dump_json(), encoding="utf-8")
    jobs_mod._write_record(lib, "9" * 32, jobs_mod.JobRecord(doc_id=1, kind="part", part_id=2))
    tell = AsyncMock()
    monkeypatch.setattr(jobs_mod, "enqueue_message", tell)
    monkeypatch.setattr(jobs_mod, "_handle_part", AsyncMock(side_effect=RuntimeError("boom")))
    session = _FakeSession({(LibraryDoc, 1): doc, (LibraryPart, 1): part}, rows=["pending"])

    async def run() -> dict[str, int]:
        return await collect_bulk_results(
            session,  # type: ignore[arg-type]
            clean_dir=clean, jobs_dir=jobs, library_dir=lib, part_pages=5, owner_chat_id=42,
        )  # fmt: skip

    for n in (1, 2):
        counts = await run()
        assert counts["errors"] == 1 and doc.status == "processing"
        assert (clean / f"{'1' * 32}.result.json").exists()  # kept for the next run
        assert jobs_mod._read_record(lib, "1" * 32).failures == n  # type: ignore[union-attr]
    await run()
    assert doc.status == "failed"
    assert not (clean / f"{'1' * 32}.result.json").exists()
    assert (clean / "failed" / f"{'1' * 32}.result.json").exists()
    assert jobs_mod._read_record(lib, "1" * 32) is None
    assert not other.exists() and jobs_mod._read_record(lib, "9" * 32) is None  # withdrawn
    tell.assert_awaited_once()
    assert tell.await_args.args[1] == 42 and tell.await_args.kwargs["purpose"] == "library_failed"


async def test_commit_happens_before_any_job_file_is_written(tmp_path: Path):
    from techradar.library import jobs as jobs_mod

    jobs = tmp_path / "jobs"
    doc = SimpleNamespace(
        id=1, kind="pdf", status="queued", original_path=f"originals/{'a' * 64}.pdf", title="T",
        origin="library",
    )  # fmt: skip
    session = _FakeSession({(LibraryDoc, 1): doc})
    seen: list[tuple[str, int]] = []

    async def commit() -> None:
        seen.append((doc.status, len(list(jobs.glob("*.job.json")))))

    session.commit = commit  # type: ignore[method-assign]
    [job_id] = await jobs_mod.plan_doc(
        session,  # type: ignore[arg-type]
        1, jobs_dir=jobs, library_dir=tmp_path / "lib",
    )  # fmt: skip
    assert seen == [("processing", 0)]  # processing was set and committed, no job file yet
    assert (jobs / f"{job_id}.job.json").exists()


async def test_plan_doc_fails_a_doc_whose_file_name_no_job_can_carry(tmp_path: Path):
    doc = SimpleNamespace(
        id=1, kind="pdf", status="queued", original_path="originals/x.pdf", title="T"
    )
    session = _FakeSession({(LibraryDoc, 1): doc})
    from techradar.library import jobs as jobs_mod

    got = await jobs_mod.plan_doc(
        session,
        1,
        jobs_dir=tmp_path / "jobs",
        library_dir=tmp_path / "lib",
        commit=False,  # type: ignore[arg-type]
    )
    assert got == [] and doc.status == "failed" and not (tmp_path / "jobs").exists()


async def test_media_probe_without_audio_fails_the_doc():
    from techradar.library.jobs import _handle_media_probe

    for probe in (
        {"duration_s": 60.0, "has_audio": False, "has_video": True},
        {"duration_s": 60.0, "has_audio": False, "has_video": False},
    ):
        doc = _fake_doc("video")
        session = _FakeSession({})
        staged: list = []
        result = ParseResult(
            job_id="d" * 32, kind="video", status="ok", purpose="library",
            doc=CleanDoc(url="library:1", title="t", text=json.dumps(probe), lang="en"),
        )  # fmt: skip
        await _handle_media_probe(session, doc, result, staged=staged)  # type: ignore[arg-type]
        assert doc.status == "failed" and not session.added and not staged


def test_withdraw_removes_job_files_records_and_waiting_results_but_not_originals(tmp_path: Path):
    from techradar.library import jobs as jobs_mod

    lib, jobs, clean = tmp_path / "lib", tmp_path / "jobs", tmp_path / "clean"
    (lib / "originals").mkdir(parents=True)
    original = lib / "originals" / f"{'a' * 64}.pdf"
    original.write_bytes(b"%PDF")
    jobs.mkdir()
    clean.mkdir()

    def mk(job_id: str, doc_id: int, *, job_file: bool, result: bool) -> None:
        jobs_mod._write_record(lib, job_id, jobs_mod.JobRecord(doc_id=doc_id, kind="part"))
        if job_file:
            job = ParseJob(
                job_id=job_id, kind="pdf", raw_name=f"{'a' * 64}.pdf", url=f"library:{doc_id}",
                source_id=0, origin="library", purpose="library", mode="part", doc_id=doc_id,
            )  # fmt: skip
            (jobs / f"{job_id}.job.json").write_text(job.model_dump_json(), encoding="utf-8")
        if result:
            _write_result(clean, job_id)

    mk("1" * 32, 5, job_file=True, result=False)
    mk("2" * 32, 5, job_file=False, result=True)  # record and result, no job file
    mk("3" * 32, 6, job_file=True, result=True)  # another doc: untouched
    jobs_mod._withdraw_doc_jobs(5, jobs, lib, clean)
    assert not list(jobs.glob(f"{'1' * 32}*")) and not list(clean.glob(f"{'2' * 32}*"))
    assert jobs_mod._read_record(lib, "1" * 32) is None
    assert jobs_mod._read_record(lib, "2" * 32) is None
    assert jobs_mod._read_record(lib, "3" * 32) is not None
    assert (jobs / f"{'3' * 32}.job.json").exists() and (clean / f"{'3' * 32}.result.json").exists()
    assert original.exists()


def test_rejected_docs_lose_their_text_and_media_but_keep_the_original(tmp_path: Path):
    from techradar.library import jobs as jobs_mod

    lib = tmp_path / "lib"
    (lib / "text" / "7" / "parts").mkdir(parents=True)
    (lib / "text" / "7" / "parts" / "1.md").write_text("x")
    (lib / "media" / "7" / "audio").mkdir(parents=True)
    (lib / "text" / "8").mkdir(parents=True)
    (lib / "originals").mkdir()
    (lib / "originals" / "o.pdf").write_bytes(b"x")
    jobs_mod._remove_doc_files(lib, 7)
    assert not (lib / "text" / "7").exists() and not (lib / "media" / "7").exists()
    assert (lib / "text" / "8").exists() and (lib / "originals" / "o.pdf").exists()


async def test_collector_queues_indexing_after_the_commit(tmp_path: Path):
    """A settled doc: the hook runs after the commit and before the result file is removed."""
    from techradar.library import jobs as jobs_mod

    lib, clean, jobs = tmp_path / "lib", tmp_path / "clean", tmp_path / "jobs"
    doc = _fake_doc("docx")
    jobs_mod._write_record(lib, "c" * 32, jobs_mod.JobRecord(doc_id=1, kind="full"))
    cut = CleanDoc(url="library:1", title="t", text="# One\nalpha", lang="en", truncated=True)
    clean.mkdir()
    res = ParseResult(job_id="c" * 32, kind="docx", status="ok", purpose="library", doc=cut)
    (clean / f"{'c' * 32}.result.json").write_text(res.model_dump_json(), encoding="utf-8")
    session = _FakeSession({(LibraryDoc, 1): doc}, rows=[])
    events: list[str] = []
    commit = session.commit

    async def tracked_commit() -> None:
        events.append("commit")
        await commit()

    async def hook(doc_id: int) -> None:
        events.append(f"hook {doc_id} result_exists={(clean / f'{"c" * 32}.result.json').exists()}")

    session.commit = tracked_commit  # type: ignore[method-assign]
    counts = await collect_bulk_results(
        session,  # type: ignore[arg-type]
        clean_dir=clean, jobs_dir=jobs, library_dir=lib, part_pages=5, on_chapters_ready=hook,
    )  # fmt: skip
    assert events == ["commit", "hook 1 result_exists=True"]
    assert counts["truncated"] == 1 and counts["handled"] == 1
    assert not (clean / f"{'c' * 32}.result.json").exists()


async def test_a_failing_hook_keeps_the_result_for_the_next_run(tmp_path: Path):
    from techradar.library import jobs as jobs_mod

    lib, clean, jobs = tmp_path / "lib", tmp_path / "clean", tmp_path / "jobs"
    doc = _fake_doc("docx")
    jobs_mod._write_record(lib, "c" * 32, jobs_mod.JobRecord(doc_id=1, kind="full"))
    clean.mkdir()
    res = ParseResult(
        job_id="c" * 32, kind="docx", status="ok", purpose="library",
        doc=CleanDoc(url="library:1", title="t", text="alpha", lang="en"),
    )  # fmt: skip
    (clean / f"{'c' * 32}.result.json").write_text(res.model_dump_json(), encoding="utf-8")
    session = _FakeSession({(LibraryDoc, 1): doc}, rows=[])
    hook = AsyncMock(side_effect=RuntimeError("queue down"))
    counts = await collect_bulk_results(
        session,  # type: ignore[arg-type]
        clean_dir=clean, jobs_dir=jobs, library_dir=lib, part_pages=5, on_chapters_ready=hook,
    )  # fmt: skip
    assert counts["errors"] == 1
    assert (clean / f"{'c' * 32}.result.json").exists()
    assert jobs_mod._read_record(lib, "c" * 32) is not None


# --- more database tests -------------------------------------------------------------


async def _outbox(session: AsyncSession, doc_id: int, purpose: str) -> list[Outbox]:
    rows = await session.execute(
        select(Outbox).where(Outbox.purpose == purpose, Outbox.ref_id == doc_id)
    )
    return list(rows.scalars())


async def _collect_owner(session: AsyncSession, d: Dirs, on_chapters_ready=None) -> dict[str, int]:
    return await collect_bulk_results(
        session,
        clean_dir=d.clean,
        jobs_dir=d.jobs,
        library_dir=d.lib,
        part_pages=PART_PAGES,
        commit=False,
        owner_chat_id=1,
        on_chapters_ready=on_chapters_ready,
    )


@pytest.mark.db
async def test_failed_doc_tells_the_owner_once(session: AsyncSession, dirs: Dirs):
    doc = await _doc(session)
    [probe_id] = await plan_doc(
        session, doc.id, jobs_dir=dirs.jobs, library_dir=dirs.lib, commit=False
    )
    _write_result(dirs.clean, probe_id, text=json.dumps({"n_pages": MAX_PDF_PAGES + 1}))
    await _collect_owner(session, dirs)
    assert doc.status == "failed" and await _parts(session, doc.id) == []
    [msg] = await _outbox(session, doc.id, "library_failed")
    assert "A Book" in msg.text and msg.chat_id == 1
    # the same result again (crash before it was removed) does not tell twice
    _write_result(dirs.clean, probe_id, text=json.dumps({"n_pages": MAX_PDF_PAGES + 1}))
    jobs_mod_record = {"doc_id": doc.id, "kind": "probe", "part_id": None}
    (dirs.lib / "jobs").mkdir(parents=True, exist_ok=True)
    (dirs.lib / "jobs" / f"{probe_id}.json").write_text(json.dumps(jobs_mod_record))
    await _collect_owner(session, dirs)
    assert len(await _outbox(session, doc.id, "library_failed")) == 1


@pytest.mark.db
async def test_quarantine_removes_the_docs_text_and_records(session: AsyncSession, dirs: Dirs):
    doc = await _planned_with_probe(session, dirs, 12)
    parts = await _parts(session, doc.id)
    _write_result(dirs.clean, parts[1].job_id, text=_pages(6, 10))
    await _collect(session, dirs)  # part 2 text is on disk now
    assert (dirs.lib / "text" / str(doc.id) / "parts" / "2.md").exists()
    media = dirs.lib / "media" / str(doc.id)
    media.mkdir(parents=True)
    _write_result(dirs.clean, parts[0].job_id, status="quarantined", text=None)
    await _collect(session, dirs)
    assert doc.status == "quarantined"
    assert not (dirs.lib / "text" / str(doc.id)).exists() and not media.exists()
    assert not list((dirs.lib / "jobs").glob("*.json"))  # every record of the doc is gone


@pytest.mark.db
async def test_chapters_ready_hook_runs_once_when_the_last_part_settles(
    session: AsyncSession, dirs: Dirs
):
    seen: list[int] = []

    async def hook(doc_id: int) -> None:
        seen.append(doc_id)

    doc = await _planned_with_probe(session, dirs, 10)
    p1, p2 = await _parts(session, doc.id)
    _write_result(dirs.clean, p1.job_id, text=_pages(1, 5))
    await _collect_owner(session, dirs, hook)
    assert seen == []  # one part still pending
    _write_result(dirs.clean, p2.job_id, text=_pages(6, 10))
    await _collect_owner(session, dirs, hook)
    assert seen == [doc.id]
    assert (await _parts(session, doc.id))[1].status == "done"


@pytest.mark.db
async def test_truncated_part_is_counted_and_noted(session: AsyncSession, dirs: Dirs):
    doc = await _planned_with_probe(session, dirs, 5)
    [p1] = await _parts(session, doc.id)
    cut = CleanDoc(url="library:1", title="t", text=_pages(1, 3), lang="en", truncated=True)
    res = ParseResult(job_id=p1.job_id, kind="pdf", status="ok", purpose="library", doc=cut)
    (dirs.clean / f"{p1.job_id}.result.json").write_text(res.model_dump_json(), encoding="utf-8")
    counts = await _collect(session, dirs)
    assert counts["truncated"] == 1
    [row] = (
        (await session.execute(select(LibraryChapter).where(LibraryChapter.doc_id == doc.id)))
        .scalars()
        .all()
    )
    text = (dirs.lib / row.text_path).read_text()
    assert "cut off" in text and row.missing_pages == [4, 5]


@pytest.mark.db
async def test_resume_counts_an_attempt_per_lost_job_and_fails_the_part_at_three(
    session: AsyncSession, doc_with_parts, dirs: Dirs
):
    part4 = (await _parts(session, doc_with_parts.id))[3]
    for attempt in (1, 2):
        got = await resume_parts(
            session, doc_with_parts.id, jobs_dir=dirs.jobs, library_dir=dirs.lib, commit=False
        )
        assert got == [4] and part4.attempts == attempt and part4.status == "pending"
        (dirs.jobs / f"{part4.job_id}.job.json").unlink()  # lost again
    got = await resume_parts(
        session,
        doc_with_parts.id,
        jobs_dir=dirs.jobs,
        library_dir=dirs.lib,
        commit=False,
        owner_chat_id=1,
    )
    assert got == [] and part4.attempts == 3 and part4.status == "failed"
    # the other three parts are done, so the doc got its chapters (page 16-20 missing)
    [*_, last] = (
        (
            await session.execute(
                select(LibraryChapter)
                .where(LibraryChapter.doc_id == doc_with_parts.id)
                .order_by(LibraryChapter.ordinal)
            )
        )
        .scalars()
        .all()
    )
    assert last.missing_pages and last.page_end == 20


@pytest.mark.db
async def test_resume_fails_a_part_queued_over_24_hours_ago(
    session: AsyncSession, doc_with_parts, dirs: Dirs
):
    part4 = (await _parts(session, doc_with_parts.id))[3]
    record = dirs.lib / "jobs" / f"{part4.job_id}.json"
    old = record.stat().st_mtime - 25 * 3600
    os.utime(record, (old, old))
    (dirs.jobs / f"{part4.job_id}.job.json").touch()  # the job is still waiting in the queue
    got = await resume_parts(
        session,
        doc_with_parts.id,
        jobs_dir=dirs.jobs,
        library_dir=dirs.lib,
        commit=False,
        owner_chat_id=1,
    )
    assert got == [] and part4.status == "failed"
    [msg] = await _outbox(session, doc_with_parts.id, "library_part_failed")
    assert "4" in msg.text


@pytest.mark.db
async def test_resume_leaves_a_young_waiting_part_alone(
    session: AsyncSession, doc_with_parts, dirs: Dirs
):
    part4 = (await _parts(session, doc_with_parts.id))[3]
    (dirs.jobs / f"{part4.job_id}.job.json").touch()
    got = await resume_parts(
        session, doc_with_parts.id, jobs_dir=dirs.jobs, library_dir=dirs.lib, commit=False
    )
    assert got == [] and part4.status == "pending" and part4.attempts == 0


@pytest.mark.db
async def test_resume_does_not_plan_a_doc_that_was_just_queued(session: AsyncSession, dirs: Dirs):
    doc = await _doc(session, status="queued")
    out = await resume_all(session, jobs_dir=dirs.jobs, library_dir=dirs.lib, commit=False)
    assert doc.id not in out and doc.status == "queued" and not dirs.jobs.exists()


@pytest.mark.db
async def test_a_lost_probe_is_rewritten_then_the_doc_fails_after_three_losses(
    session: AsyncSession, dirs: Dirs
):
    doc = await _doc(session, status="processing")
    for _ in range(3):  # the first run queues a probe; the next two see it waiting
        await resume_parts(session, doc.id, jobs_dir=dirs.jobs, library_dir=dirs.lib, commit=False)
    [job_file] = dirs.jobs.glob("*.job.json")  # same record: not queued twice
    assert doc.status == "processing"
    for n in (1, 2):
        job_file.unlink()
        await resume_parts(session, doc.id, jobs_dir=dirs.jobs, library_dir=dirs.lib, commit=False)
        assert job_file.exists() and doc.status == "processing", n
    job_file.unlink()
    await resume_parts(
        session, doc.id, jobs_dir=dirs.jobs, library_dir=dirs.lib, commit=False, owner_chat_id=1
    )
    assert doc.status == "failed" and not job_file.exists()
    assert len(await _outbox(session, doc.id, "library_failed")) == 1


@pytest.mark.db
async def test_resume_all_skips_a_doc_that_raises_and_still_heals_the_rest(
    session: AsyncSession, dirs: Dirs, monkeypatch: pytest.MonkeyPatch
):
    from techradar.library import jobs as jobs_mod

    bad = await _doc(session, status="processing")
    good = await _doc(session, status="processing")
    real = jobs_mod._resume_doc

    async def flaky(session_, doc_id, **kw):
        if doc_id == bad.id:
            raise RuntimeError("boom")
        return await real(session_, doc_id, **kw)

    monkeypatch.setattr(jobs_mod, "_resume_doc", flaky)
    out = await resume_all(session, jobs_dir=dirs.jobs, library_dir=dirs.lib, commit=False)
    assert good.id in out and bad.id not in out
    [job_file] = dirs.jobs.glob("*.job.json")
    assert json.loads(job_file.read_text())["doc_id"] == good.id
