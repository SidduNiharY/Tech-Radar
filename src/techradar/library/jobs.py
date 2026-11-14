"""Bulk library jobs (Phase 2c Task 4): plan parse jobs, collect results, build chapters.

How job ids are tracked
-----------------------
Parse results carry only a job id, so every library job gets a small record
`<library_dir>/jobs/<job_id>.json` = {"doc_id", "kind": probe|part|full|media, "part_id", ...}.
The record is written BEFORE the job file in the parse-jobs dir, so a job never exists
without a record. The record is deleted only after its result was applied and committed.
Records live on the library volume, so they survive restarts. The bulk collector only
looks at result files that have a record, and the news collector skips every result whose
purpose is not "news", so the two never consume each other's files.

Commit first, files second
--------------------------
Handlers never write job files themselves: they stage them (`staged`). The collector
commits the database change and only then writes the staged records and job files, so a
job file never exists for a state that was rolled back. A crash between the commit and the
file write leaves a `pending` part (or a `processing` doc) with no job file; `resume_*`
rewrites it. Likewise `plan_doc` commits `processing` before it queues anything.

Pending parts are also in `library_parts` (status pending, job_id set). A crash leaves one of:
- a part whose job file is gone and has no result: `resume_parts` rewrites it (and counts an
  attempt; the third lost job fails the part);
- a result already applied (part no longer pending, or doc already has parts): the collector
  sees the stale result, deletes it and does nothing else, so parts are never duplicated.

One bad result never blocks the others: each result is applied in its own savepoint and
transaction. A result that raises is retried on the next run; the third failure moves the file
to `clean/failed/`, fails the doc and tells the owner.

Status ownership: this module sets `processing` (plan_doc), `rejected`/`quarantined`/`failed`.
After chapters are built the doc STAYS `processing` with `pages` set (and chapter rows
present); the `on_chapters_ready` hook (the worker's index job) then indexes the chapters and
defers the summaries; Task 7 sets `ready`.

Video/audio (Task 5) work like PDFs: a probe (duration), then one `media` job per 600 s segment
(a `library_parts` row with ts_start/ts_end). Each segment result is validated strictly
(media_results.py); its audio file path goes into `result_path` and its slides are merged into
`media/<doc_id>/slides.json`. When all segments settled the doc becomes
`awaiting_transcription` (transcripts come with phase 6), the original video is deleted unless
`keep_media`, and the owner gets one message. A probe without an audio track fails the doc.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import re
import shutil
import stat
import uuid
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, ValidationError, field_validator
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import LibraryChapter, LibraryDoc, LibraryPart
from techradar.fetcher.store import write_job
from techradar.library.chapters import (
    ChapterSpec,
    _page_map,
    assemble_from_pages,
    detect_chapters,
    missing_in_pages,
    write_chapter_text,
)
from techradar.library.media_results import (
    Slide,
    parse_probe,
    parse_segment_result,
    segment_bounds,
)
from techradar.library.parts import split_pdf_parts
from techradar.library.quarantine import flag_doc
from techradar.messaging.outbox import enqueue_message
from techradar.schemas.pipeline import ParseJob, ParseResult
from techradar.security.text import sanitize_text

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
MAX_RESULT_FAILURES = 3
MAX_TITLE = 300
MAX_PDF_PAGES = 5000
MAX_OUTLINE = 500
MAX_OUTLINE_LEVEL = 10
MAX_CHAPTERS = 500
MAX_TEXT_CHARS = 100_000  # CleanDoc.text limit: a longer text arrives cut
QUEUED_STUCK_S = 600
PART_MAX_AGE_S = 24 * 3600
JobRecordKind = Literal["probe", "part", "full", "media"]
_PAGE_MARKER = re.compile(r"^<!-- page (\d+) -->$")
_H1 = re.compile(r"^# +(\S.*)$")
_EPUB_CHAPTER = re.compile(r"^<!-- chapter \d+: (.*?) -->$")
_JOB_ID = re.compile(r"[0-9a-f]{32}")
_FULL_KIND = {"docx": "docx", "epub": "epub", "html": "page"}
# Only transient failures are worth another try: a file that is too large or of a type the
# parser does not support fails the same way every time.
_RETRYABLE = {"error", "timeout"}
_FINAL_STATUSES = ("rejected", "quarantined", "failed", "ready", "awaiting_transcription")
_TRUNCATION_NOTE = (
    f"> This text was cut off here: only the first {MAX_TEXT_CHARS:,} characters were read."
)

ChaptersReady = Callable[[int], Awaitable[None]]


class JobRecord(BaseModel):
    doc_id: int
    kind: JobRecordKind
    part_id: int | None = None
    failures: int = 0  # times applying this job's result raised (see collect_bulk_results)
    requeues: int = 0  # times a lost probe/full job was written again (see resume_parts)


class _OutlineItem(BaseModel):
    """Local mirror of the parser's OutlineEntry (the parser package is off limits here)."""

    title: str
    page: int
    level: int


class _Probe(BaseModel):
    """The parser's PDF probe. It is untrusted: `n_pages` is bounded (a probe over the cap
    fails the doc) and the outline is cleaned, not rejected: bad entries are dropped."""

    n_pages: Annotated[int, Field(strict=True, ge=1, le=MAX_PDF_PAGES)]
    outline: list[_OutlineItem] = []

    @field_validator("outline", mode="before")
    @classmethod
    def _clean_outline(cls, raw: Any, info: Any) -> list[_OutlineItem]:
        n_pages = info.data.get("n_pages")
        if not isinstance(raw, list) or not isinstance(n_pages, int):
            return []
        items: list[_OutlineItem] = []
        for entry in raw:
            if len(items) >= MAX_OUTLINE:
                break
            try:
                item = _OutlineItem.model_validate(entry)
            except ValidationError:
                continue
            title = _clean_title(item.title)
            if not title or not 1 <= item.page <= n_pages:
                continue
            if not 1 <= item.level <= MAX_OUTLINE_LEVEL:
                continue
            items.append(_OutlineItem(title=title, page=item.page, level=item.level))
        return items


@dataclass
class _Staged:
    """A job file and its record, written only after the database change is committed."""

    job: ParseJob
    record: JobRecord


@dataclass
class _Applied:
    """What applying one result did, for the collector to finish after the commit."""

    stale: bool = False
    chapters_built: bool = False
    truncated: bool = False
    withdraw: bool = False  # the doc stopped: remove its other jobs
    drop_files: bool = False  # rejected/quarantined: remove its text and media


# --- small file helpers ---------------------------------------------------------


def _records_dir(library_dir: Path) -> Path:
    return library_dir / "jobs"


def _atomic_write(path: Path, data: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o640)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(data)
    os.replace(tmp, path)


def _write_record(library_dir: Path, job_id: str, rec: JobRecord) -> None:
    _atomic_write(_records_dir(library_dir) / f"{job_id}.json", rec.model_dump_json())


def _read_record(library_dir: Path, job_id: str) -> JobRecord | None:
    if not _JOB_ID.fullmatch(job_id):  # the id comes from a file name: never build a path from it
        return None
    try:
        return JobRecord.model_validate_json(
            (_records_dir(library_dir) / f"{job_id}.json").read_text(encoding="utf-8")
        )
    except OSError, ValidationError:
        return None


def _drop_record(library_dir: Path, job_id: str) -> None:
    if _JOB_ID.fullmatch(job_id):
        (_records_dir(library_dir) / f"{job_id}.json").unlink(missing_ok=True)


def _new_job_id() -> str:
    return uuid.uuid4().hex


def _text_dir(library_dir: Path, doc_id: int) -> Path:
    return library_dir / "text" / str(doc_id)


def _media_dir(library_dir: Path, doc_id: int) -> Path:
    return library_dir / "media" / str(doc_id)


def _clean_title(title: str) -> str:
    return " ".join(sanitize_text(title).split())[:MAX_TITLE]


def _with_truncation_note(text: str, truncated: bool) -> str:
    """The text with a visible note at its end when the parser cut it at its size limit."""
    return f"{text.rstrip()}\n\n{_TRUNCATION_NOTE}" if truncated else text


def _make_job(
    doc: LibraryDoc,
    *,
    job_id: str,
    mode: Literal["full", "probe", "part", "media"],
    kind: str,
    part: LibraryPart | None = None,
) -> ParseJob:
    return ParseJob(
        job_id=job_id,
        kind=kind,  # type: ignore[arg-type]
        raw_name=Path(doc.original_path).name,
        url=f"library:{doc.id}",
        source_id=0,
        origin="library",
        purpose="library",
        mode=mode,
        page_start=part.page_start if part else None,
        page_end=part.page_end if part else None,
        ts_start=part.ts_start if part else None,
        ts_end=part.ts_end if part else None,
        doc_id=doc.id,
        part_id=part.id if part else None,
    )


def _stage(
    staged: list[_Staged],
    doc: LibraryDoc,
    *,
    job_id: str,
    rec_kind: JobRecordKind,
    mode: Literal["full", "probe", "part", "media"],
    kind: str,
    part: LibraryPart | None = None,
    requeues: int = 0,
) -> None:
    """Prepare a job (pure data); `_write_staged` writes it after the commit."""
    record = JobRecord(
        doc_id=doc.id, kind=rec_kind, part_id=part.id if part else None, requeues=requeues
    )
    staged.append(_Staged(_make_job(doc, job_id=job_id, mode=mode, kind=kind, part=part), record))


def _write_staged(staged: Sequence[_Staged], jobs_dir: Path, library_dir: Path) -> None:
    """Record first, then the job file: the order that makes restarts safe."""
    for item in staged:
        _write_record(library_dir, item.job.job_id, item.record)
        write_job(item.job, jobs_dir)


async def _tell_owner(
    session: AsyncSession, owner_chat_id: int | None, text: str, *, purpose: str, doc_id: int
) -> None:
    if owner_chat_id is not None:
        await enqueue_message(session, owner_chat_id, text, purpose=purpose, ref_id=doc_id)


async def _tell_if_failed(
    session: AsyncSession, doc: LibraryDoc, before: str, owner_chat_id: int | None
) -> bool:
    """Tell the owner once when a doc just turned `failed`; returns whether it did."""
    if doc.status != "failed" or before == "failed":
        return False
    await _tell_owner(
        session,
        owner_chat_id,
        f"I couldn't read {_clean_title(doc.title)}: processing it failed, so it is not in your "
        "library. You can send it again.",
        purpose="library_failed",
        doc_id=doc.id,
    )
    return True


# --- plan -----------------------------------------------------------------------


async def _plan(
    session: AsyncSession, doc_id: int, staged: list[_Staged], owner_chat_id: int | None = None
) -> list[str]:
    doc = await session.get(LibraryDoc, doc_id)
    if doc is None or doc.status != "queued":
        return []
    job_id = _new_job_id()
    try:
        if doc.kind == "pdf":
            _stage(staged, doc, job_id=job_id, rec_kind="probe", mode="probe", kind="pdf")
        elif doc.kind in _FULL_KIND:
            _stage(
                staged, doc, job_id=job_id, rec_kind="full", mode="full", kind=_FULL_KIND[doc.kind]
            )
        else:  # video, audio: a probe first, then one media job per segment
            _stage(staged, doc, job_id=job_id, rec_kind="probe", mode="probe", kind=doc.kind)
    except ValidationError:  # a stored file name no parse job can carry: it never will
        logger.warning("library doc %s cannot be queued: its stored file name is invalid", doc.id)
        doc.status = "failed"
        await _tell_if_failed(session, doc, "queued", owner_chat_id)
        await session.flush()
        return []
    doc.status = "processing"
    await session.flush()
    return [job_id]


async def _commit(session: AsyncSession, commit: bool) -> None:
    if commit:
        await session.commit()
    else:
        await session.flush()


async def plan_doc(
    session: AsyncSession,
    doc_id: int,
    *,
    jobs_dir: Path,
    library_dir: Path,
    commit: bool = True,
    owner_chat_id: int | None = None,
) -> list[str]:
    """Write the first job(s) for a queued doc and set it `processing`. Returns job ids.

    `processing` is committed BEFORE the job file is written, so a job file never belongs to a
    doc that is still `queued` (and a crash in between is healed by `resume_all`).
    `commit=False` only flushes (for tests that roll back).
    """
    staged: list[_Staged] = []
    ids = await _plan(session, doc_id, staged, owner_chat_id)
    await _commit(session, commit)
    _write_staged(staged, jobs_dir, library_dir)
    return ids


# --- text splitting (pure) ------------------------------------------------------


def split_full_text(kind: str, doc_title: str, text: str) -> list[tuple[str, str]]:
    """(title, text) chapters of a whole-document result.

    EPUB: split on `<!-- chapter N: title -->`. DOCX/HTML: split on level-1 `# ` headings.
    Text before the first marker/heading becomes its own chapter titled with the doc title;
    with no markers the whole text is one chapter titled with the doc title. At most
    MAX_CHAPTERS chapters: the rest is merged into the last one.
    """
    pattern = _EPUB_CHAPTER if kind == "epub" else _H1
    keep_marker = kind != "epub"
    chapters: list[tuple[str, list[str]]] = [(_clean_title(doc_title), [])]
    for line in text.splitlines():
        m = pattern.match(line.strip() if kind == "epub" else line)
        if m:
            chapters.append((_clean_title(m.group(1)) or _clean_title(doc_title), []))
            if not keep_marker:
                continue
        chapters[-1][1].append(line)
    out = [(t, "\n".join(lines).strip()) for t, lines in chapters]
    out = [(t, body) for t, body in out if body] or [(_clean_title(doc_title), text.strip())]
    if len(out) > MAX_CHAPTERS:
        merged = "\n\n".join(body for _, body in out[MAX_CHAPTERS - 1 :])
        out = [*out[: MAX_CHAPTERS - 1], (out[MAX_CHAPTERS - 1][0], merged)]
    return out


def _page_headings(pages: Mapping[int, str]) -> list[tuple[int, int, str]]:
    """Level-1 `# ` lines inside a page's block, as (page, 1, title)."""
    found: list[tuple[int, int, str]] = []
    for n in sorted(pages):
        for line in pages[n].splitlines()[1:]:  # line 0 is the page marker
            h = _H1.match(line)
            if h:
                found.append((n, 1, h.group(1).strip()))
    return found


def _cap_specs(specs: list[ChapterSpec]) -> list[ChapterSpec]:
    """At most MAX_CHAPTERS chapters: the pages of the rest join the last one."""
    if len(specs) <= MAX_CHAPTERS:
        return specs
    head = specs[:MAX_CHAPTERS]
    head[-1] = head[-1].model_copy(update={"page_end": specs[-1].page_end})
    return head


# --- chapters -------------------------------------------------------------------

ChapterRow = tuple[ChapterSpec | None, str, str, list[int]]


def _chapter_rows(
    pages: Mapping[int, str], specs: Sequence[ChapterSpec], failed_pages: Sequence[int]
) -> list[ChapterRow]:
    """(spec, title, text, missing pages) per chapter from ONE page map (never re-split)."""
    failed = set(failed_pages)
    return [
        (ch, ch.title, assemble_from_pages(pages, ch, failed), missing_in_pages(pages, ch, failed))
        for ch in specs
    ]


async def _replace_chapters(
    session: AsyncSession,
    doc_id: int,
    library_dir: Path,
    chapters: Sequence[ChapterRow],
) -> None:
    await session.execute(delete(LibraryChapter).where(LibraryChapter.doc_id == doc_id))
    for ordinal, (spec, title, text, missing) in enumerate(chapters, start=1):
        path = write_chapter_text(library_dir, doc_id, ordinal, text)
        session.add(
            LibraryChapter(
                doc_id=doc_id,
                ordinal=ordinal,
                title=title,
                page_start=spec.page_start if spec else None,
                page_end=spec.page_end if spec else None,
                text_path=path.relative_to(library_dir).as_posix(),
                missing_pages=missing,
            )
        )
    await session.flush()


async def build_chapters(
    session: AsyncSession, doc_id: int, *, library_dir: Path, part_pages: int
) -> int:
    """Chapters of a PDF from its part texts, the probe outline and level-1 headings.

    Rewrites `library_chapters` and chapter text files (safe to re-run). The doc stays
    `processing`: the index job and Task 7 (summaries) set `ready`. Returns the chapter count.
    """
    doc = await session.get(LibraryDoc, doc_id)
    if doc is None:
        return 0
    parts = (
        (
            await session.execute(
                select(LibraryPart)
                .where(LibraryPart.doc_id == doc_id)
                .order_by(LibraryPart.ordinal)
            )
        )
        .scalars()
        .all()
    )
    part_texts: list[tuple[int, int, str]] = []
    failed_pages: list[int] = []
    for p in parts:
        first, last = p.page_start or 0, p.page_end or -1
        if p.status == "done" and p.result_path:
            try:
                text = (library_dir / p.result_path).read_text(encoding="utf-8")
                part_texts.append((first, last, text))
                continue
            except OSError:
                logger.warning("part text missing: doc %s part %s", doc_id, p.ordinal)
        failed_pages.extend(range(first, last + 1))
    pages = _page_map(part_texts)
    n_pages = doc.pages or max((p.page_end or 0 for p in parts), default=0)
    outline: list[_OutlineItem] = []
    probe_path = _text_dir(library_dir, doc_id) / "probe.json"
    with contextlib.suppress(OSError, ValidationError):
        outline = _Probe.model_validate_json(probe_path.read_text(encoding="utf-8")).outline
    specs = detect_chapters(n_pages, outline, _page_headings(pages), part_pages)  # type: ignore[arg-type]
    rows = _chapter_rows(pages, _cap_specs(specs), failed_pages)
    await _replace_chapters(session, doc_id, library_dir, rows)
    doc.pages = n_pages or doc.pages
    await session.flush()
    return len(rows)


async def _build_full_chapters(
    session: AsyncSession, doc: LibraryDoc, text: str, library_dir: Path
) -> int:
    rows: list[ChapterRow] = [
        (None, t, body, []) for t, body in split_full_text(doc.kind, doc.title, text)
    ]
    await _replace_chapters(session, doc.id, library_dir, rows)
    return len(rows)


def _part_job_args(doc: LibraryDoc) -> tuple[JobRecordKind, Literal["part", "media"], str]:
    """(record kind, parse mode, parser kind) of a part job of this doc."""
    if doc.kind in ("video", "audio"):
        return "media", "media", doc.kind
    return "part", "part", "pdf"


def _result_files(clean_dir: Path) -> list[Path]:
    return sorted(clean_dir.glob("*.result.json")) if clean_dir.exists() else []


# --- stopping a doc -------------------------------------------------------------


def _withdraw_doc_jobs(
    doc_id: int, jobs_dir: Path, library_dir: Path, clean_dir: Path | None = None
) -> None:
    """Stop a doc: delete its job files, their records and any result waiting for them.

    Job files are matched on their own doc_id (purpose library), records on theirs: a job
    file can outlive its record (the probe's) and a record can outlive its job file. The
    original file stays. A straggler result that arrives later has no record and is ignored.
    """
    if jobs_dir.exists():
        for job_file in jobs_dir.glob("*.job.json"):
            try:
                job = ParseJob.model_validate_json(job_file.read_text(encoding="utf-8"))
            except OSError, ValidationError:
                continue
            if job.purpose == "library" and job.doc_id == doc_id:
                job_file.unlink(missing_ok=True)
                _drop_record(library_dir, job.job_id)
    rec_dir = _records_dir(library_dir)
    for rec_file in rec_dir.glob("*.json") if rec_dir.exists() else []:
        rec = _read_record(library_dir, rec_file.stem)
        if rec is None or rec.doc_id != doc_id:
            continue
        (jobs_dir / f"{rec_file.stem}.job.json").unlink(missing_ok=True)
        if clean_dir is not None:
            (clean_dir / f"{rec_file.stem}.result.json").unlink(missing_ok=True)
        rec_file.unlink(missing_ok=True)


def _remove_doc_files(library_dir: Path, doc_id: int) -> None:
    """Delete everything derived from a doc's text and media (parts, chapters, audio, slides).

    Used for rejected and quarantined docs so nothing of them stays indexable. The original
    stays (quarantine keeps it for the owner's review).
    """
    for path in (_text_dir(library_dir, doc_id), _media_dir(library_dir, doc_id)):
        if path.is_symlink():
            logger.warning("not removing %s: it is a symlink", path)
            continue
        shutil.rmtree(path, ignore_errors=True)


def _save_text(path: Path, text: str) -> None:
    _atomic_write(path, text)
    path.chmod(0o640)


# --- handlers (PDF, whole documents) ----------------------------------------------


async def _handle_probe(
    session: AsyncSession,
    doc: LibraryDoc,
    result: ParseResult,
    *,
    staged: list[_Staged],
    library_dir: Path,
    part_pages: int,
) -> None:
    existing = (
        await session.execute(select(LibraryPart.id).where(LibraryPart.doc_id == doc.id).limit(1))
    ).first()
    if existing is not None:  # already applied (crash before the result file was removed)
        return
    if result.status != "ok" or result.doc is None:
        doc.status = "failed"
        return
    try:
        probe = _Probe.model_validate_json(result.doc.text)
    except ValidationError as exc:  # includes a page count over MAX_PDF_PAGES
        logger.warning("doc %s: unusable probe (%d problems)", doc.id, exc.error_count())
        doc.status = "failed"
        return
    _save_text(_text_dir(library_dir, doc.id) / "probe.json", probe.model_dump_json())
    doc.pages = probe.n_pages
    parts = [
        LibraryPart(
            doc_id=doc.id,
            ordinal=s.ordinal,
            page_start=s.page_start,
            page_end=s.page_end,
            status="pending",
            attempts=0,
            job_id=_new_job_id(),
        )
        for s in split_pdf_parts(probe.n_pages, part_pages)
    ]
    session.add_all(parts)
    await session.flush()
    for p in parts:
        _stage(staged, doc, job_id=p.job_id or "", rec_kind="part", mode="part", kind="pdf", part=p)


async def _handle_part(
    session: AsyncSession,
    doc: LibraryDoc,
    rec: JobRecord,
    result: ParseResult,
    *,
    staged: list[_Staged],
    library_dir: Path,
    part_pages: int,
) -> tuple[bool, bool]:
    """Apply one part result. Returns (applied, chapters built): `applied` is False for a stale
    result; the chapters are built when this part was the last one pending."""
    part = await session.get(LibraryPart, rec.part_id) if rec.part_id else None
    if part is None or part.status != "pending" or part.job_id != result.job_id:
        return False, False  # stale: already applied or superseded by a retry
    if result.status in ("ok", "empty"):
        path = _text_dir(library_dir, doc.id) / "parts" / f"{part.ordinal}.md"
        text = result.doc.text if result.doc else ""
        _save_text(path, _with_truncation_note(text, bool(result.doc and result.doc.truncated)))
        part.result_path = path.relative_to(library_dir).as_posix()
        part.status = "done"
    else:
        part.attempts += 1
        if result.status in _RETRYABLE and part.attempts < MAX_ATTEMPTS:
            part.job_id = _new_job_id()
            await session.flush()
            rec_kind, mode, kind = _part_job_args(doc)
            _stage(
                staged, doc, job_id=part.job_id, rec_kind=rec_kind, mode=mode, kind=kind, part=part
            )
        else:
            part.status = "failed"
    await session.flush()
    built = await _finish_if_parts_settled(
        session, doc, library_dir=library_dir, part_pages=part_pages
    )
    return True, built


async def _finish_if_parts_settled(
    session: AsyncSession, doc: LibraryDoc, *, library_dir: Path, part_pages: int
) -> bool:
    """Build chapters once no part is pending; True when chapters were built."""
    statuses = (
        (await session.execute(select(LibraryPart.status).where(LibraryPart.doc_id == doc.id)))
        .scalars()
        .all()
    )
    if not statuses or "pending" in statuses:
        return False
    if "done" not in statuses:
        doc.status = "failed"
        return False
    await build_chapters(session, doc.id, library_dir=library_dir, part_pages=part_pages)
    return True


async def _handle_full(
    session: AsyncSession, doc: LibraryDoc, result: ParseResult, *, library_dir: Path
) -> bool:
    """Apply a whole-document (docx/epub/html) result; True when chapters were built."""
    chapter_exists = (
        await session.execute(
            select(LibraryChapter.id).where(LibraryChapter.doc_id == doc.id).limit(1)
        )
    ).first()
    if chapter_exists is not None:
        return False
    if result.status != "ok" or result.doc is None:
        doc.status = "failed"
        return False
    text = _with_truncation_note(result.doc.text, result.doc.truncated)
    await _build_full_chapters(session, doc, text, library_dir)
    return True


# --- media (video, audio) -------------------------------------------------------


def _merge_slides(library_dir: Path, doc_id: int, slides: list[Slide]) -> None:
    """Append slides to media/<doc_id>/slides.json, kept sorted by ts_s, written atomically."""
    path = _media_dir(library_dir, doc_id) / "slides.json"
    existing: list[dict] = []
    with contextlib.suppress(OSError, ValueError):
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(loaded, list):
            existing = [x for x in loaded if isinstance(x, dict)]
    merged = existing + [s.model_dump() for s in slides]
    merged.sort(key=lambda x: float(x.get("ts_s", 0)))
    _save_text(path, json.dumps(merged))


def _delete_original(library_dir: Path, doc: LibraryDoc) -> None:
    """Delete a video's original: only a regular file (never a symlink) in originals/."""
    if doc.kind != "video" or doc.keep_media:
        return
    path = library_dir / doc.original_path
    try:
        if path.parent.resolve() != (library_dir / "originals").resolve():
            return
        if not stat.S_ISREG(os.lstat(path).st_mode):
            return
        os.unlink(path)
    except OSError:
        logger.warning("could not delete original of doc %s", doc.id)


async def _handle_media(
    session: AsyncSession,
    doc: LibraryDoc,
    rec: JobRecord,
    result: ParseResult,
    *,
    staged: list[_Staged],
    library_dir: Path,
    owner_chat_id: int | None,
) -> None:
    if rec.kind == "probe":
        await _handle_media_probe(session, doc, result, staged=staged)
        return
    part = await session.get(LibraryPart, rec.part_id) if rec.part_id else None
    if part is None or part.status != "pending" or part.job_id != result.job_id:
        return  # stale: already applied or superseded by a retry
    status = result.status
    seg = None
    if status == "ok":
        seg = (
            parse_segment_result(result.doc.text, part.ts_start or 0.0, part.ts_end or 0.0)
            if result.doc and part.ts_start is not None and part.ts_end is not None
            else None
        )
        if seg is None:
            status = "error"  # untrusted output that breaks the contract
    if seg is not None:
        _merge_slides(library_dir, doc.id, seg.slides)
        part.result_path = f"media/{doc.id}/{seg.audio_file}"
        part.status = "done"
    else:
        part.attempts += 1
        if status in _RETRYABLE and part.attempts < MAX_ATTEMPTS:
            part.job_id = _new_job_id()
            await session.flush()
            rec_kind, mode, kind = _part_job_args(doc)
            _stage(
                staged, doc, job_id=part.job_id, rec_kind=rec_kind, mode=mode, kind=kind, part=part
            )
        else:
            part.status = "failed"
    await session.flush()
    await _finish_media_if_settled(session, doc, library_dir, owner_chat_id)


async def _handle_media_probe(
    session: AsyncSession, doc: LibraryDoc, result: ParseResult, *, staged: list[_Staged]
) -> None:
    existing = (
        await session.execute(select(LibraryPart.id).where(LibraryPart.doc_id == doc.id).limit(1))
    ).first()
    if existing is not None:
        return
    probe = parse_probe(result.doc.text) if result.status == "ok" and result.doc else None
    # No audio track means nothing to transcribe (a silent video is of no use here).
    if probe is None or not probe.has_audio:
        doc.status = "failed"
        return
    doc.duration_s = probe.duration_s
    parts = [
        LibraryPart(
            doc_id=doc.id,
            ordinal=i,
            ts_start=start,
            ts_end=end,
            status="pending",
            attempts=0,
            job_id=_new_job_id(),
        )  # fmt: skip
        for i, (start, end) in enumerate(segment_bounds(probe.duration_s))
    ]
    session.add_all(parts)
    await session.flush()
    rec_kind, mode, kind = _part_job_args(doc)
    for p in parts:
        _stage(staged, doc, job_id=p.job_id or "", rec_kind=rec_kind, mode=mode, kind=kind, part=p)


async def _finish_media_if_settled(
    session: AsyncSession, doc: LibraryDoc, library_dir: Path, owner_chat_id: int | None
) -> None:
    statuses = (
        (await session.execute(select(LibraryPart.status).where(LibraryPart.doc_id == doc.id)))
        .scalars()
        .all()
    )
    if not statuses or "pending" in statuses:
        return
    if "done" not in statuses:
        doc.status = "failed"
        return
    doc.status = "awaiting_transcription"
    _delete_original(library_dir, doc)
    await _tell_owner(
        session,
        owner_chat_id,
        f"Got {doc.title}: audio and slides are ready; the transcript comes when phase 6 is built.",
        purpose="library_ready",
        doc_id=doc.id,
    )
    await session.flush()


# --- collect --------------------------------------------------------------------


def _was_cut(result: ParseResult) -> bool:
    """The parser kept the text and cut it at its size limit."""
    return bool(
        result.doc is not None and result.doc.truncated and result.status in ("ok", "empty")
    )


def _error_result(job_id: str) -> ParseResult:
    """Stand-in for a result file that cannot be read: the parser failed on this job."""
    return ParseResult(job_id=job_id, kind="md", status="error", purpose="library")


async def _apply_result(
    session: AsyncSession,
    doc: LibraryDoc | None,
    rec: JobRecord,
    result: ParseResult,
    *,
    staged: list[_Staged],
    library_dir: Path,
    part_pages: int,
    owner_chat_id: int | None,
) -> _Applied:
    """Change the database for one result; files are written by the caller after the commit."""
    if doc is None or doc.status in _FINAL_STATUSES:
        return _Applied(stale=True)
    if _verdict_needs_flag(result):
        await flag_doc(session, doc)
    if result.status in ("rejected", "quarantined"):
        doc.status = result.status
        await session.flush()
        return _Applied(withdraw=True, drop_files=True)
    before = doc.status
    applied = _Applied()
    if doc.kind in ("video", "audio") and rec.kind in ("probe", "media"):
        await _handle_media(
            session, doc, rec, result, staged=staged, library_dir=library_dir,
            owner_chat_id=owner_chat_id,
        )  # fmt: skip
    elif rec.kind == "probe":
        await _handle_probe(
            session, doc, result, staged=staged, library_dir=library_dir, part_pages=part_pages
        )
    elif rec.kind == "part":
        fresh, applied.chapters_built = await _handle_part(
            session, doc, rec, result, staged=staged, library_dir=library_dir,
            part_pages=part_pages,
        )  # fmt: skip
        applied.truncated = fresh and _was_cut(result)
    elif rec.kind == "full":
        applied.chapters_built = await _handle_full(session, doc, result, library_dir=library_dir)
        applied.truncated = applied.chapters_built and _was_cut(result)
    if await _tell_if_failed(session, doc, before, owner_chat_id):
        applied.withdraw = True
    return applied


_CONTENT_STATUSES = ("ok", "empty")


def _verdict_needs_flag(result: ParseResult) -> bool:
    """A result whose content is used must carry a clean gateway verdict (fail closed).

    No intake at all, a `flag`, or a verdict that contradicts an ok status (quarantine or
    reject on an ok result) all mean flagged. Only `pass` leaves the doc as it is. Results
    that carry no content (error, timeout, too_large, ...) add nothing to the library.
    """
    if result.status not in _CONTENT_STATUSES:
        return False
    return result.intake is None or result.intake.verdict != "pass"


async def _has_chapters(session: AsyncSession, doc_id: int) -> bool:
    row = (
        await session.execute(
            select(LibraryChapter.id).where(LibraryChapter.doc_id == doc_id).limit(1)
        )
    ).first()
    return row is not None


async def _give_up(
    session: AsyncSession,
    rec: JobRecord,
    rpath: Path,
    job_id: str,
    *,
    jobs_dir: Path,
    library_dir: Path,
    clean_dir: Path,
    owner_chat_id: int | None,
    commit: bool,
) -> None:
    """A result that failed MAX_RESULT_FAILURES times: fail its doc, move the file aside."""
    doc = await session.get(LibraryDoc, rec.doc_id, populate_existing=True)
    if doc is not None and doc.status not in _FINAL_STATUSES:
        before = doc.status
        doc.status = "failed"
        await _tell_if_failed(session, doc, before, owner_chat_id)
    await _commit(session, commit)
    failed_dir = clean_dir / "failed"
    failed_dir.mkdir(parents=True, exist_ok=True)
    os.replace(rpath, failed_dir / rpath.name)  # before the withdrawal, which clears clean_dir
    _withdraw_doc_jobs(rec.doc_id, jobs_dir, library_dir, clean_dir)
    _drop_record(library_dir, job_id)


async def collect_bulk_results(
    session: AsyncSession,
    *,
    clean_dir: Path,
    jobs_dir: Path,
    library_dir: Path,
    part_pages: int,
    commit: bool = True,
    owner_chat_id: int | None = None,
    on_chapters_ready: ChaptersReady | None = None,
) -> dict[str, int]:
    """Apply every result that belongs to a library job; leave all other files alone.

    Each result is applied in a savepoint and committed, then its staged job files are
    written, and only then is the result file deleted together with its job record, so a
    crash re-runs the result harmlessly (see module docstring). `commit=False` only flushes
    (for tests that roll back). `owner_chat_id` receives the "media ready" and "failed"
    messages. `on_chapters_ready(doc_id)` runs after a doc's chapters were committed (the
    worker queues the indexing job there); if it raises, the result stays for the next run.

    A result file that cannot be parsed counts as a parser `error`. A result that raises
    while being applied is rolled back, logged and retried next run; the third failure moves
    the file to `clean/failed/` and fails its doc.
    """
    counts = {"handled": 0, "skipped": 0, "stale": 0, "errors": 0, "truncated": 0}
    for rpath in _result_files(clean_dir):
        job_id = rpath.name.removesuffix(".result.json")
        rec = _read_record(library_dir, job_id)  # also rejects ids that are not 32 hex chars
        if rec is None:
            counts["skipped"] += 1  # not ours (news, clipping) or unknown
            continue
        try:
            raw = rpath.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            logger.warning("unreadable library result %s: %s", rpath.name, exc)
            counts["skipped"] += 1
            continue
        try:
            result = ParseResult.model_validate_json(raw)
        except ValidationError:
            logger.warning("unparsable library result %s: counted as a parser error", rpath.name)
            result = _error_result(job_id)
        if result.purpose != "library" or result.job_id != job_id:
            counts["skipped"] += 1
            continue
        staged: list[_Staged] = []
        try:
            async with session.begin_nested():
                doc = await session.get(LibraryDoc, rec.doc_id)
                applied = await _apply_result(
                    session, doc, rec, result, staged=staged, library_dir=library_dir,
                    part_pages=part_pages, owner_chat_id=owner_chat_id,
                )  # fmt: skip
                if (
                    applied.stale
                    and on_chapters_ready is not None
                    and doc is not None
                    and doc.status == "processing"
                    and rec.kind in ("part", "full")
                ):
                    # Re-run of a result whose chapters are committed: queue indexing again
                    # in case the first attempt never got through.
                    applied.chapters_built = await _has_chapters(session, doc.id)
            await _commit(session, commit)
        except Exception:
            logger.exception("library result %s failed (failure %d)", rpath.name, rec.failures + 1)
            counts["errors"] += 1
            failures = rec.failures + 1
            try:
                if failures < MAX_RESULT_FAILURES:
                    _write_record(
                        library_dir, job_id, rec.model_copy(update={"failures": failures})
                    )
                else:
                    await _give_up(
                        session, rec, rpath, job_id, jobs_dir=jobs_dir, library_dir=library_dir,
                        clean_dir=clean_dir, owner_chat_id=owner_chat_id, commit=commit,
                    )  # fmt: skip
            except Exception:
                logger.exception("could not record the failure of library result %s", rpath.name)
            continue
        counts["stale" if applied.stale else "handled"] += 1
        counts["truncated"] += applied.truncated
        if applied.truncated:
            logger.warning("doc %s: parsed text was cut at its size limit", rec.doc_id)
        try:
            _write_staged(staged, jobs_dir, library_dir)  # a lost write is healed by resume_*
            if applied.withdraw:
                _withdraw_doc_jobs(rec.doc_id, jobs_dir, library_dir, clean_dir)
            if applied.drop_files:
                _remove_doc_files(library_dir, rec.doc_id)
        except OSError:
            logger.exception("library files of doc %s could not be updated", rec.doc_id)
        if applied.chapters_built and on_chapters_ready is not None:
            try:
                await on_chapters_ready(rec.doc_id)
            except Exception:
                logger.exception("could not queue indexing for doc %s; will retry", rec.doc_id)
                counts["errors"] += 1
                continue
        rpath.unlink(missing_ok=True)
        _drop_record(library_dir, job_id)
    return counts


# --- resume ---------------------------------------------------------------------


@dataclass
class _Resumed:
    requeued: list[int] = field(default_factory=list)
    chapters_built: bool = False


def _record_age_s(library_dir: Path, job_id: str, now_ts: float) -> float | None:
    """Seconds since this job's record was written (= since the job was queued)."""
    try:
        return now_ts - (_records_dir(library_dir) / f"{job_id}.json").stat().st_mtime
    except OSError:
        return None


async def _resume_doc(
    session: AsyncSession,
    doc_id: int,
    *,
    jobs_dir: Path,
    library_dir: Path,
    clean_dir: Path | None,
    part_pages: int,
    owner_chat_id: int | None,
    now_ts: float,
    staged: list[_Staged],
) -> _Resumed:
    out = _Resumed()
    doc = await session.get(LibraryDoc, doc_id)
    if doc is None or doc.status != "processing":
        return out
    before = doc.status
    parts = (
        (
            await session.execute(
                select(LibraryPart)
                .where(LibraryPart.doc_id == doc_id, LibraryPart.status == "pending")
                .order_by(LibraryPart.ordinal)
            )
        )
        .scalars()
        .all()
    )
    failed_parts: list[LibraryPart] = []
    timed_out: list[int] = []
    for p in parts:
        if not p.job_id:
            p.job_id = _new_job_id()
        if clean_dir is not None and (clean_dir / f"{p.job_id}.result.json").exists():
            continue  # the collector will take it
        age = _record_age_s(library_dir, p.job_id, now_ts)
        if age is not None and age > PART_MAX_AGE_S:
            p.status = "failed"  # queued over a day ago and still nothing: give up on it
            timed_out.append(p.ordinal)
            failed_parts.append(p)
            continue
        if (jobs_dir / f"{p.job_id}.job.json").exists():
            continue
        p.attempts += 1  # a lost job counts as an attempt, so losing it forever ends
        if p.attempts >= MAX_ATTEMPTS:
            p.status = "failed"
            failed_parts.append(p)
            continue
        rec_kind, mode, kind = _part_job_args(doc)
        _stage(staged, doc, job_id=p.job_id, rec_kind=rec_kind, mode=mode, kind=kind, part=p)
        out.requeued.append(p.ordinal)
    await session.flush()
    if failed_parts:
        if doc.kind in ("video", "audio"):
            await _finish_media_if_settled(session, doc, library_dir, owner_chat_id)
        else:
            out.chapters_built = await _finish_if_parts_settled(
                session, doc, library_dir=library_dir, part_pages=part_pages
            )
    if timed_out and doc.status != "failed":
        where = ", ".join(str(n) for n in timed_out)
        await _tell_owner(
            session,
            owner_chat_id,
            f"Part {where} of {_clean_title(doc.title)} never finished and was skipped. "
            "The rest of it is still being prepared.",
            purpose="library_part_failed",
            doc_id=doc.id,
        )
    if doc.status == "processing":
        await _requeue_single_job(session, doc, jobs_dir, library_dir, clean_dir, staged)
    await _tell_if_failed(session, doc, before, owner_chat_id)
    await session.flush()
    return out


async def _requeue_single_job(
    session: AsyncSession,
    doc: LibraryDoc,
    jobs_dir: Path,
    library_dir: Path,
    clean_dir: Path | None,
    staged: list[_Staged],
) -> None:
    """Probe (PDF, media) or full (docx/epub/html) job lost before it produced anything.

    A doc with no such record gets a new job; a record whose job file and result are both
    gone gets its job written again. The third lost job of a doc fails it.
    """
    if doc.kind in ("pdf", "video", "audio"):
        rec_kind: JobRecordKind = "probe"
        mode: Literal["full", "probe", "part", "media"] = "probe"
        kind = doc.kind
        done = (
            await session.execute(
                select(LibraryPart.id).where(LibraryPart.doc_id == doc.id).limit(1)
            )
        ).first()
    elif doc.kind in _FULL_KIND:
        rec_kind, mode, kind = "full", "full", _FULL_KIND[doc.kind]
        done = (
            await session.execute(
                select(LibraryChapter.id).where(LibraryChapter.doc_id == doc.id).limit(1)
            )
        ).first()
    else:
        return
    if done is not None:
        return
    rec_dir = _records_dir(library_dir)
    existing: list[tuple[str, JobRecord]] = []
    for f in rec_dir.glob("*.json") if rec_dir.exists() else []:
        rec = _read_record(library_dir, f.stem)
        if rec is not None and rec.doc_id == doc.id and rec.kind == rec_kind:
            existing.append((f.stem, rec))
    if not existing:
        _stage(staged, doc, job_id=_new_job_id(), rec_kind=rec_kind, mode=mode, kind=kind)
        return
    for job_id, rec in existing:
        waiting = (clean_dir is not None and (clean_dir / f"{job_id}.result.json").exists()) or (
            jobs_dir / f"{job_id}.job.json"
        ).exists()
        if waiting:
            continue
        if rec.requeues + 1 >= MAX_ATTEMPTS:
            doc.status = "failed"
            return
        _stage(
            staged, doc, job_id=job_id, rec_kind=rec_kind, mode=mode, kind=kind,
            requeues=rec.requeues + 1,
        )  # fmt: skip


async def _finish_resume(
    session: AsyncSession,
    commit: bool,
    staged: list[_Staged],
    jobs_dir: Path,
    library_dir: Path,
) -> None:
    await _commit(session, commit)
    _write_staged(staged, jobs_dir, library_dir)


async def resume_parts(
    session: AsyncSession,
    doc_id: int,
    *,
    jobs_dir: Path,
    library_dir: Path,
    clean_dir: Path | None = None,
    part_pages: int = 25,
    owner_chat_id: int | None = None,
    on_chapters_ready: ChaptersReady | None = None,
    commit: bool = True,
    now: datetime | None = None,
) -> list[int]:
    """Re-queue work lost to a restart; returns the ordinals of re-queued parts.

    - every `pending` part whose job file is missing (and, when `clean_dir` is given, whose
      result is not already waiting there) gets its job rewritten and one attempt counted;
      the third lost job fails the part;
    - a `pending` part queued more than 24 hours ago (by its job record) is failed and the
      owner told;
    - a `processing` doc with no parts and no probe job record gets a new probe job; a probe or
      full job whose record exists but whose job file and result are both gone is rewritten
      (the returned list covers parts only).

    The database change is committed before any job file is written.
    """
    staged: list[_Staged] = []
    now_ts = (now or datetime.now(UTC)).timestamp()
    res = await _resume_doc(
        session, doc_id, jobs_dir=jobs_dir, library_dir=library_dir, clean_dir=clean_dir,
        part_pages=part_pages, owner_chat_id=owner_chat_id, now_ts=now_ts, staged=staged,
    )  # fmt: skip
    await _finish_resume(session, commit, staged, jobs_dir, library_dir)
    if res.chapters_built and on_chapters_ready is not None:
        await on_chapters_ready(doc_id)
    return res.requeued


async def resume_all(
    session: AsyncSession,
    *,
    jobs_dir: Path,
    library_dir: Path,
    clean_dir: Path | None = None,
    part_pages: int = 25,
    owner_chat_id: int | None = None,
    on_chapters_ready: ChaptersReady | None = None,
    commit: bool = True,
    now: datetime | None = None,
    queued_min_age_s: float = QUEUED_STUCK_S,
) -> dict[int, list[int]]:
    """Heal every stuck doc; returns {doc_id: re-queued ordinals}.

    - a `queued` doc older than `queued_min_age_s` (its deferred plan job was lost) is planned;
    - `resume_parts` runs for every `processing` doc.

    Each doc is handled in its own savepoint and commit: one doc that raises is logged and
    skipped, the others still run.
    """
    when = now or datetime.now(UTC)
    queued_ids = (
        (
            await session.execute(
                select(LibraryDoc.id)
                .where(
                    LibraryDoc.status == "queued",
                    LibraryDoc.created_at < when - timedelta(seconds=queued_min_age_s),
                )
                .order_by(LibraryDoc.id)
            )
        )
        .scalars()
        .all()
    )
    processing_ids = (
        (
            await session.execute(
                select(LibraryDoc.id)
                .where(LibraryDoc.status == "processing")
                .order_by(LibraryDoc.id)
            )
        )
        .scalars()
        .all()
    )
    out: dict[int, list[int]] = {}

    async def guarded(doc_id: int, work: Callable[[list[_Staged]], Awaitable[_Resumed]]) -> None:
        staged: list[_Staged] = []
        try:
            async with session.begin_nested():
                res = await work(staged)
            await _commit(session, commit)
        except Exception:
            logger.exception("resume of library doc %s failed", doc_id)
            return
        out[doc_id] = res.requeued
        try:
            _write_staged(staged, jobs_dir, library_dir)
        except OSError:
            logger.exception("job files of library doc %s could not be written", doc_id)
            return
        if res.chapters_built and on_chapters_ready is not None:
            try:
                await on_chapters_ready(doc_id)
            except Exception:
                logger.exception("could not queue indexing for doc %s", doc_id)

    for doc_id in queued_ids:

        async def plan(staged: list[_Staged], doc_id: int = doc_id) -> _Resumed:
            await _plan(session, doc_id, staged, owner_chat_id)
            return _Resumed()

        await guarded(doc_id, plan)
    for doc_id in processing_ids:

        async def resume(staged: list[_Staged], doc_id: int = doc_id) -> _Resumed:
            return await _resume_doc(
                session, doc_id, jobs_dir=jobs_dir, library_dir=library_dir, clean_dir=clean_dir,
                part_pages=part_pages, owner_chat_id=owner_chat_id, now_ts=when.timestamp(),
                staged=staged,
            )  # fmt: skip

        await guarded(doc_id, resume)
    return out
