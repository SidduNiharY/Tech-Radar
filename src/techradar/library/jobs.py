"""Bulk library jobs (Phase 2c Task 4): plan parse jobs, collect results, build chapters.

How job ids are tracked
-----------------------
Parse results carry only a job id, so every library job gets a small record
`<library_dir>/jobs/<job_id>.json` = {"doc_id", "kind": probe|part|full|media, "part_id"}.
The record is written BEFORE the job file in the parse-jobs dir, so a job never exists
without a record. The record is deleted only after its result was applied and committed.
Records live on the library volume, so they survive restarts. The bulk collector only
looks at result files that have a record, and the news collector skips every result whose
purpose is not "news", so the two never consume each other's files. (The old
`collect_library_results` in rag/indexer.py deletes every library result; the worker no
longer calls it.)

Pending parts are also in `library_parts` (status pending, job_id set). A crash leaves one of:
- a part whose job file is gone and has no result: `resume_parts` rewrites it;
- a result already applied (part no longer pending, or doc already has parts): the collector
  sees the stale result, deletes it and does nothing else, so parts are never duplicated.

Status ownership: this module sets `processing` (plan_doc), `rejected`/`quarantined`/`failed`.
After chapters are built the doc STAYS `processing` with `pages` set (and chapter rows
present); Task 6 (indexing and summaries) sets `ready`.

Video/audio (Task 5) work like PDFs: a probe (duration), then one `media` job per 600 s segment
(a `library_parts` row with ts_start/ts_end). Each segment result is validated strictly
(media_results.py); its audio file path goes into `result_path` and its slides are merged into
`media/<doc_id>/slides.json`. When all segments settled the doc becomes
`awaiting_transcription` (transcripts come with phase 6), the original video is deleted unless
`keep_media`, and the owner gets one message.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import re
import stat
import uuid
from collections.abc import Sequence
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ValidationError
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import LibraryChapter, LibraryDoc, LibraryPart
from techradar.fetcher.store import write_job
from techradar.library.chapters import (
    ChapterSpec,
    assemble_chapter_text,
    detect_chapters,
    missing_pages,
    write_chapter_text,
)
from techradar.library.media_results import (
    Slide,
    parse_probe,
    parse_segment_result,
    segment_bounds,
)
from techradar.library.parts import split_pdf_parts
from techradar.messaging.outbox import enqueue_message
from techradar.schemas.pipeline import ParseJob, ParseResult

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
MAX_TITLE = 300
JobRecordKind = Literal["probe", "part", "full", "media"]
_PAGE_MARKER = re.compile(r"^<!-- page (\d+) -->$")
_H1 = re.compile(r"^# +(\S.*)$")
_EPUB_CHAPTER = re.compile(r"^<!-- chapter \d+: (.*?) -->$")
_FULL_KIND = {"docx": "docx", "epub": "epub", "html": "page"}
_RETRYABLE = {"error", "too_large", "timeout", "unsupported"}


class JobRecord(BaseModel):
    doc_id: int
    kind: JobRecordKind
    part_id: int | None = None


class _OutlineItem(BaseModel):
    """Local mirror of the parser's OutlineEntry (the parser package is off limits here)."""

    title: str
    page: int
    level: int


class _Probe(BaseModel):
    n_pages: int
    outline: list[_OutlineItem] = []


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
    try:
        return JobRecord.model_validate_json(
            (_records_dir(library_dir) / f"{job_id}.json").read_text(encoding="utf-8")
        )
    except OSError, ValidationError:
        return None


def _drop_record(library_dir: Path, job_id: str) -> None:
    (_records_dir(library_dir) / f"{job_id}.json").unlink(missing_ok=True)


def _new_job_id() -> str:
    return uuid.uuid4().hex


def _text_dir(library_dir: Path, doc_id: int) -> Path:
    return library_dir / "text" / str(doc_id)


def _clean_title(title: str) -> str:
    return " ".join(title.split())[:MAX_TITLE]


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


def _queue(
    doc: LibraryDoc,
    jobs_dir: Path,
    library_dir: Path,
    *,
    job_id: str,
    rec_kind: JobRecordKind,
    mode: Literal["full", "probe", "part", "media"],
    kind: str,
    part: LibraryPart | None = None,
) -> None:
    """Record first, then the job file: the order that makes restarts safe."""
    _write_record(
        library_dir,
        job_id,
        JobRecord(doc_id=doc.id, kind=rec_kind, part_id=part.id if part else None),
    )
    write_job(_make_job(doc, job_id=job_id, mode=mode, kind=kind, part=part), jobs_dir)


# --- plan -----------------------------------------------------------------------


async def plan_doc(
    session: AsyncSession, doc_id: int, *, jobs_dir: Path, library_dir: Path
) -> list[str]:
    """Write the first job(s) for a queued doc and set it `processing`. Returns job ids."""
    doc = await session.get(LibraryDoc, doc_id)
    if doc is None or doc.status != "queued":
        return []
    job_id = _new_job_id()
    if doc.kind == "pdf":
        _queue(
            doc, jobs_dir, library_dir, job_id=job_id, rec_kind="probe", mode="probe", kind="pdf"
        )
    elif doc.kind in _FULL_KIND:
        _queue(
            doc,
            jobs_dir,
            library_dir,
            job_id=job_id,
            rec_kind="full",
            mode="full",
            kind=_FULL_KIND[doc.kind],
        )
    else:  # video, audio: a probe first, then one media job per segment
        _queue(
            doc, jobs_dir, library_dir, job_id=job_id, rec_kind="probe", mode="probe", kind=doc.kind
        )
    doc.status = "processing"
    await session.flush()
    return [job_id]


# --- text splitting (pure) ------------------------------------------------------


def split_full_text(kind: str, doc_title: str, text: str) -> list[tuple[str, str]]:
    """(title, text) chapters of a whole-document result.

    EPUB: split on `<!-- chapter N: title -->`. DOCX/HTML: split on level-1 `# ` headings.
    Text before the first marker/heading becomes its own chapter titled with the doc title;
    with no markers the whole text is one chapter titled with the doc title.
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
    return [(t, body) for t, body in out if body] or [(_clean_title(doc_title), text.strip())]


def _page_headings(part_texts: dict[int, str]) -> list[tuple[int, int, str]]:
    """Level-1 `# ` lines that follow a page marker, as (page, 1, title)."""
    found: list[tuple[int, int, str]] = []
    for ordinal in sorted(part_texts):
        page: int | None = None
        for line in part_texts[ordinal].splitlines():
            marker = _PAGE_MARKER.match(line.strip())
            if marker:
                page = int(marker.group(1))
                continue
            h = _H1.match(line)
            if h and page is not None:
                found.append((page, 1, h.group(1).strip()))
    return found


# --- chapters -------------------------------------------------------------------


async def _replace_chapters(
    session: AsyncSession,
    doc_id: int,
    library_dir: Path,
    chapters: Sequence[tuple[ChapterSpec | None, str, str, list[int]]],
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
    `processing`: Task 6 (indexing, summaries) sets `ready`. Returns the chapter count.
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
    part_texts: dict[int, str] = {}
    failed_pages: list[int] = []
    for p in parts:
        if p.status == "done" and p.result_path:
            try:
                part_texts[p.ordinal] = (library_dir / p.result_path).read_text(encoding="utf-8")
            except OSError:
                logger.warning("part text missing: doc %s part %s", doc_id, p.ordinal)
                failed_pages.extend(range(p.page_start or 0, (p.page_end or -1) + 1))
        else:
            failed_pages.extend(range(p.page_start or 0, (p.page_end or -1) + 1))
    n_pages = doc.pages or max((p.page_end or 0 for p in parts), default=0)
    outline: list[_OutlineItem] = []
    probe_path = _text_dir(library_dir, doc_id) / "probe.json"
    with contextlib.suppress(OSError, ValidationError):
        outline = _Probe.model_validate_json(probe_path.read_text(encoding="utf-8")).outline
    specs = detect_chapters(n_pages, outline, _page_headings(part_texts), part_pages)  # type: ignore[arg-type]
    rows = [
        (
            ch,
            ch.title,
            assemble_chapter_text(part_texts, ch, failed_pages),
            missing_pages(part_texts, ch, failed_pages),
        )
        for ch in specs
    ]
    await _replace_chapters(session, doc_id, library_dir, rows)
    doc.pages = n_pages or doc.pages
    await session.flush()
    return len(rows)


async def _build_full_chapters(
    session: AsyncSession, doc: LibraryDoc, text: str, library_dir: Path
) -> int:
    rows = [(None, t, body, []) for t, body in split_full_text(doc.kind, doc.title, text)]
    await _replace_chapters(session, doc.id, library_dir, rows)
    return len(rows)


def _part_job_args(doc: LibraryDoc) -> tuple[JobRecordKind, Literal["part", "media"], str]:
    """(record kind, parse mode, parser kind) of a part job of this doc."""
    if doc.kind in ("video", "audio"):
        return "media", "media", doc.kind
    return "part", "part", "pdf"


def _result_files(clean_dir: Path) -> list[Path]:
    return sorted(clean_dir.glob("*.result.json")) if clean_dir.exists() else []


# --- collect --------------------------------------------------------------------


def _withdraw_doc_jobs(doc_id: int, jobs_dir: Path, library_dir: Path) -> None:
    """Stop a doc: delete every job file in jobs_dir that belongs to it.

    Matches on the job file's own doc_id (purpose library), not on records: a record is gone
    once its result was consumed, yet that job file can still linger (e.g. the probe's).
    Records stay so stragglers are consumed as stale.
    """
    if not jobs_dir.exists():
        return
    for job_file in jobs_dir.glob("*.job.json"):
        try:
            job = ParseJob.model_validate_json(job_file.read_text(encoding="utf-8"))
        except OSError, ValidationError:
            continue
        if job.purpose == "library" and job.doc_id == doc_id:
            job_file.unlink(missing_ok=True)


def _save_text(path: Path, text: str) -> None:
    _atomic_write(path, text)
    path.chmod(0o640)


async def _handle_probe(
    session: AsyncSession,
    doc: LibraryDoc,
    result: ParseResult,
    *,
    jobs_dir: Path,
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
    except ValidationError:
        doc.status = "failed"
        return
    if probe.n_pages <= 0:
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
        _queue(
            doc,
            jobs_dir,
            library_dir,
            job_id=p.job_id,
            rec_kind="part",
            mode="part",
            kind="pdf",
            part=p,
        )


async def _handle_part(
    session: AsyncSession,
    doc: LibraryDoc,
    rec: JobRecord,
    result: ParseResult,
    *,
    jobs_dir: Path,
    library_dir: Path,
    part_pages: int,
) -> None:
    part = await session.get(LibraryPart, rec.part_id) if rec.part_id else None
    if part is None or part.status != "pending" or part.job_id != result.job_id:
        return  # stale: already applied or superseded by a retry
    if result.status in ("ok", "empty"):
        path = _text_dir(library_dir, doc.id) / "parts" / f"{part.ordinal}.md"
        _save_text(path, result.doc.text if result.doc else "")
        part.result_path = path.relative_to(library_dir).as_posix()
        part.status = "done"
    else:
        part.attempts += 1
        if result.status in _RETRYABLE and part.attempts < MAX_ATTEMPTS:
            part.job_id = _new_job_id()
            await session.flush()
            rec_kind, mode, kind = _part_job_args(doc)
            _queue(
                doc, jobs_dir, library_dir,
                job_id=part.job_id, rec_kind=rec_kind, mode=mode, kind=kind, part=part,
            )  # fmt: skip
        else:
            part.status = "failed"
    await session.flush()
    await _finish_if_parts_settled(session, doc, library_dir=library_dir, part_pages=part_pages)


async def _finish_if_parts_settled(
    session: AsyncSession, doc: LibraryDoc, *, library_dir: Path, part_pages: int
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
    await build_chapters(session, doc.id, library_dir=library_dir, part_pages=part_pages)


async def _handle_full(
    session: AsyncSession, doc: LibraryDoc, result: ParseResult, *, library_dir: Path
) -> None:
    chapter_exists = (
        await session.execute(
            select(LibraryChapter.id).where(LibraryChapter.doc_id == doc.id).limit(1)
        )
    ).first()
    if chapter_exists is not None:
        return
    if result.status != "ok" or result.doc is None:
        doc.status = "failed"
        return
    await _build_full_chapters(session, doc, result.doc.text, library_dir)


# --- media (video, audio) -------------------------------------------------------


def _media_dir(library_dir: Path, doc_id: int) -> Path:
    return library_dir / "media" / str(doc_id)


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
    jobs_dir: Path,
    library_dir: Path,
    owner_chat_id: int | None,
) -> None:
    if rec.kind == "probe":
        await _handle_media_probe(session, doc, result, jobs_dir=jobs_dir, library_dir=library_dir)
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
            _queue(
                doc, jobs_dir, library_dir,
                job_id=part.job_id, rec_kind=rec_kind, mode=mode, kind=kind, part=part,
            )  # fmt: skip
        else:
            part.status = "failed"
    await session.flush()
    await _finish_media_if_settled(session, doc, library_dir, owner_chat_id)


async def _handle_media_probe(
    session: AsyncSession,
    doc: LibraryDoc,
    result: ParseResult,
    *,
    jobs_dir: Path,
    library_dir: Path,
) -> None:
    existing = (
        await session.execute(select(LibraryPart.id).where(LibraryPart.doc_id == doc.id).limit(1))
    ).first()
    if existing is not None:
        return
    probe = parse_probe(result.doc.text) if result.status == "ok" and result.doc else None
    if probe is None or not (probe.has_audio or probe.has_video):
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
        _queue(
            doc, jobs_dir, library_dir, job_id=p.job_id or "", rec_kind=rec_kind, mode=mode,
            kind=kind, part=p,
        )  # fmt: skip


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
    if owner_chat_id is not None:
        await enqueue_message(
            session,
            owner_chat_id,
            f"Got {doc.title}: audio and slides are ready; "
            "the transcript comes when phase 6 is built.",
            purpose="library_ready",
            ref_id=doc.id,
        )
    await session.flush()


async def collect_bulk_results(
    session: AsyncSession,
    *,
    clean_dir: Path,
    jobs_dir: Path,
    library_dir: Path,
    part_pages: int,
    commit: bool = True,
    owner_chat_id: int | None = None,
) -> dict[str, int]:
    """Apply every result that belongs to a library job; leave all other files alone.

    Each result is applied, committed, and only then deleted together with its job record,
    so a crash re-runs the result harmlessly (see module docstring). `commit=False` only
    flushes (for tests that roll back). `owner_chat_id` receives the "media ready" message.
    """
    counts = {"handled": 0, "skipped": 0, "stale": 0}
    for rpath in _result_files(clean_dir):
        job_id = rpath.name.removesuffix(".result.json")
        rec = _read_record(library_dir, job_id)
        if rec is None:
            counts["skipped"] += 1  # not ours (news, clipping) or unknown
            continue
        try:
            result = ParseResult.model_validate_json(rpath.read_text(encoding="utf-8"))
        except (OSError, ValidationError) as exc:
            logger.warning("unreadable library result %s: %s", rpath, exc)
            counts["skipped"] += 1
            continue
        if result.purpose != "library" or result.job_id != job_id:
            counts["skipped"] += 1
            continue
        doc = await session.get(LibraryDoc, rec.doc_id)
        if doc is None or doc.status in (
            "rejected",
            "quarantined",
            "failed",
            "ready",
            "awaiting_transcription",
        ):
            counts["stale"] += 1
        elif result.status in ("rejected", "quarantined"):
            doc.status = result.status
            await session.flush()
            _withdraw_doc_jobs(doc.id, jobs_dir, library_dir)
            counts["handled"] += 1
        else:
            if doc.kind in ("video", "audio") and rec.kind in ("probe", "media"):
                await _handle_media(
                    session, doc, rec, result, jobs_dir=jobs_dir, library_dir=library_dir,
                    owner_chat_id=owner_chat_id,
                )  # fmt: skip
            elif rec.kind == "probe":
                await _handle_probe(
                    session, doc, result, jobs_dir=jobs_dir, library_dir=library_dir,
                    part_pages=part_pages,
                )  # fmt: skip
            elif rec.kind == "part":
                await _handle_part(
                    session, doc, rec, result, jobs_dir=jobs_dir, library_dir=library_dir,
                    part_pages=part_pages,
                )  # fmt: skip
            elif rec.kind == "full":
                await _handle_full(session, doc, result, library_dir=library_dir)
            counts["handled"] += 1
        if commit:
            await session.commit()
        else:
            await session.flush()
        rpath.unlink(missing_ok=True)
        _drop_record(library_dir, job_id)
    return counts


# --- resume ---------------------------------------------------------------------


async def resume_parts(
    session: AsyncSession,
    doc_id: int,
    *,
    jobs_dir: Path,
    library_dir: Path,
    clean_dir: Path | None = None,
) -> list[int]:
    """Re-queue work lost to a restart; returns the ordinals of re-queued parts.

    - every `pending` part whose job file is missing (and, when `clean_dir` is given, whose
      result is not already waiting there) gets its job rewritten;
    - a `processing` PDF with no parts and no probe job record gets a new probe job; a probe or
      full job whose record exists but whose job file and result are both gone is rewritten
      (the returned list covers parts only).
    """
    doc = await session.get(LibraryDoc, doc_id)
    if doc is None or doc.status != "processing":
        return []
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
    requeued: list[int] = []
    for p in parts:
        if not p.job_id:
            p.job_id = _new_job_id()
        if (jobs_dir / f"{p.job_id}.job.json").exists():
            continue
        if clean_dir is not None and (clean_dir / f"{p.job_id}.result.json").exists():
            continue
        rec_kind, mode, kind = _part_job_args(doc)
        _queue(
            doc, jobs_dir, library_dir, job_id=p.job_id, rec_kind=rec_kind, mode=mode, kind=kind,
            part=p,
        )  # fmt: skip
        requeued.append(p.ordinal)
    await _requeue_single_job(session, doc, jobs_dir, library_dir, clean_dir)
    await session.flush()
    return requeued


async def _requeue_single_job(
    session: AsyncSession,
    doc: LibraryDoc,
    jobs_dir: Path,
    library_dir: Path,
    clean_dir: Path | None,
) -> None:
    """Probe (PDF) or full (docx/epub/html) job lost before it produced anything."""
    if doc.kind in ("pdf", "video", "audio"):
        rec_kind: JobRecordKind = "probe"
        done = (
            await session.execute(
                select(LibraryPart.id).where(LibraryPart.doc_id == doc.id).limit(1)
            )
        ).first()
        mode: Literal["full", "probe", "part", "media"] = "probe"
        kind = "pdf" if doc.kind == "pdf" else doc.kind
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
    existing = [
        f.stem
        for f in (rec_dir.glob("*.json") if rec_dir.exists() else [])
        if (r := _read_record(library_dir, f.stem)) and r.doc_id == doc.id and r.kind == rec_kind
    ]
    if not existing:
        _queue(
            doc,
            jobs_dir,
            library_dir,
            job_id=_new_job_id(),
            rec_kind=rec_kind,
            mode=mode,
            kind=kind,
        )
        return
    for job_id in existing:
        lost = not (jobs_dir / f"{job_id}.job.json").exists() and not (
            clean_dir is not None and (clean_dir / f"{job_id}.result.json").exists()
        )
        if lost:
            _queue(
                doc, jobs_dir, library_dir, job_id=job_id, rec_kind=rec_kind, mode=mode, kind=kind
            )


async def resume_all(
    session: AsyncSession, *, jobs_dir: Path, library_dir: Path, clean_dir: Path | None = None
) -> dict[int, list[int]]:
    """`resume_parts` for every `processing` doc; returns {doc_id: re-queued ordinals}."""
    ids = (
        (await session.execute(select(LibraryDoc.id).where(LibraryDoc.status == "processing")))
        .scalars()
        .all()
    )
    out: dict[int, list[int]] = {}
    for doc_id in ids:
        out[doc_id] = await resume_parts(
            session, doc_id, jobs_dir=jobs_dir, library_dir=library_dir, clean_dir=clean_dir
        )
    return out
