"""GATE past papers from `library-inbox/gate/<year>/` (Phase 8 Task 2 wiring).

The owner drops an official paper and its answer key side by side:
`gate/<year>/<paper>-<year>.pdf` and `gate/<year>/<paper>-<year>-key.pdf` (for example
`gate/2024/cs1-2024.pdf`). Both are untrusted bytes with untrusted names.

Taking a pair (worker, queue `io`):
- Files are read the safe way of library/inbox.py (exams/inbox.py): never through a link,
  only the scanned inode, a size cap checked before reading.
- The folder must be a four-digit year in range and the name must match the pattern
  above with the same year; anything else goes to `rejected/`. The paper code and year
  come from that strict match, never from file content, and no file name reaches a job:
  the job's url is `library:gate/<year>/<PAPER>` and its raw name is `<sha256>.pdf`.
- Each file must be a PDF by its bytes (a ZIP renamed `.pdf` is refused).
- Both files are copied (hashed while copying) into `raw/`, a pair record is written to
  `library/exam-jobs/` (the parser cannot write there), then the two `purpose="pyq"` parse
  jobs, and only then do the sources move to `done/`.

The parser sandbox (no network, 120 s per job, SEC-06) runs both PDFs through the Intake
Gateway. Collecting (worker): when both results are in, each must be `ok` with the
verdict `pass` (a flagged file is never used for questions); the paper's text goes to
`split_questions`, the key's text to `parse_answer_key`, and every question with a valid
key is stored in `pyq_questions` (tag_status `none`). Exam, year and paper come from the
record, never from the parser's output.

SEC: SEC-06, SEC-18, SEC-43, SEC-57.
"""

from __future__ import annotations

import contextlib
import logging
import math
import os
import re
import stat
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import PyqQuestion
from techradar.exams.inbox import move_scanned, open_scanned, real_subdir, too_large
from techradar.exams.pyq import parse_answer_key, split_questions
from techradar.fetcher.store import write_job
from techradar.intake.filetype import detect_mime_in
from techradar.library.inbox import (
    MAX_NAME_CHARS,
    FileChanged,
    InboxFile,
    _copy_hashed,
    clean_text,
    stable_files,
)
from techradar.schemas.pipeline import ParseJob, ParseResult

log = logging.getLogger(__name__)

EXAM = "GATE"
GATE_DIR = "gate"
PYQ_RECORDS_DIR = "exam-jobs"  # under the library dir: the worker writes it, the parser cannot
MIN_GATE_YEAR = 1991
MAX_GATE_PDF_BYTES = 20_000_000
MAX_FILES_PER_RUN = 50
MAX_RESULT_BYTES = 2_000_000
MAX_RECORD_BYTES = 4096
PAIR_MAX_AGE_S = 24 * 3600  # the retention job removes results older than a day
MAX_QUESTIONS = 200
MAX_QUESTION_CHARS = 4000
MAX_OPTIONS = 6
MAX_OPTION_CHARS = 500
_YEAR_DIR = re.compile(r"[0-9]{4}")
# cs-2024.pdf, CS1-2024.pdf, da-2024-key.pdf
_NAME = re.compile(r"(?P<paper>[A-Za-z]{2}[12]?)-(?P<year>[0-9]{4})(?P<key>-key)?\.pdf", re.I)
_MCQ = re.compile(r"[A-D]")
_MSQ = re.compile(r"[A-D](?:;[A-D])*")
_NUM = r"-?[0-9]{1,6}(?:\.[0-9]{1,6})?"
_NAT = re.compile(rf"({_NUM})(?: to ({_NUM}))?")
_RECORD = re.compile(r"[0-9a-f]{32}\.json")
_NOFOLLOW = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK

Send = Callable[[str], Awaitable[None]]
Role = Literal["paper", "key"]


class PyqPair(BaseModel):
    """The worker's record of one queued pair (written before the job files)."""

    exam: Literal["GATE"] = EXAM
    year: Annotated[int, Field(ge=MIN_GATE_YEAR, le=2100)]
    paper: Annotated[str, Field(pattern=r"^[A-Z]{2}[12]?$")]
    paper_job: Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")]
    key_job: Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")]
    created: float


class GateName(BaseModel):
    year: int
    paper: str
    role: Role


def max_gate_year(now: float) -> int:
    return datetime.fromtimestamp(now, UTC).year + 1


def parse_gate_name(rel_parts: tuple[str, ...], now: float) -> GateName | str:
    """The year, paper and role of `<year>/<name>` under gate/, or why it is refused."""
    if len(rel_parts) != 2:
        return "put each paper in gate/<year>/, for example gate/2024/cs-2024.pdf"
    year_dir, name = rel_parts
    if not _YEAR_DIR.fullmatch(year_dir):
        return "the folder must be a year, for example gate/2024/"
    year = int(year_dir)
    if not MIN_GATE_YEAR <= year <= max_gate_year(now):
        return f"the year must be between {MIN_GATE_YEAR} and {max_gate_year(now)}"
    m = _NAME.fullmatch(name)
    if m is None:
        return "name it <paper>-<year>.pdf or <paper>-<year>-key.pdf, for example cs-2024.pdf"
    if int(m.group("year")) != year:
        return f"the year in the name does not match the folder {year_dir}"
    return GateName(year=year, paper=m.group("paper").upper(), role="key" if m["key"] else "paper")


def _job(job_id: str, raw_name: str, name: GateName) -> ParseJob:
    suffix = "-key" if name.role == "key" else ""
    return ParseJob(
        job_id=job_id,
        kind="pdf",
        raw_name=raw_name,
        url=f"library:gate/{name.year}/{name.paper}{suffix}",
        source_id=0,
        origin="library",
        purpose="pyq",
    )


def _atomic_write(dir_path: Path, name: str, data: str) -> None:
    """Write dir_path/name through a private temp file; never follows a link."""
    dir_path.mkdir(parents=True, exist_ok=True, mode=0o750)
    dfd = os.open(dir_path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        tmp = f".{uuid.uuid4().hex}.tmp"
        wfd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o640, dir_fd=dfd)
        try:
            os.write(wfd, data.encode("utf-8"))
            os.fsync(wfd)
        finally:
            os.close(wfd)
        os.replace(tmp, name, src_dir_fd=dfd, dst_dir_fd=dfd)
    finally:
        os.close(dfd)


def _check_pdf(inbox: Path, f: InboxFile) -> str | None:
    """None when the file is a PDF by its bytes within the cap, else the reason."""
    if f.size > MAX_GATE_PDF_BYTES:
        return too_large(f.size, MAX_GATE_PDF_BYTES)  # never read
    with open_scanned(inbox, f) as (_dir_fd, _name, fh):
        head = fh.read(8)
        if head.startswith(b"PK\x03\x04") or detect_mime_in(fh) != "application/pdf":
            return "it is not a PDF"
    return None


def _copy_to_raw(inbox: Path, f: InboxFile, raw_dir: Path) -> str:
    """Copy the scanned file into raw/ as `<sha256>.pdf` (hashed while copying)."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    rfd = os.open(raw_dir, os.O_RDONLY | os.O_DIRECTORY)
    try:
        with open_scanned(inbox, f) as (_dir_fd, _name, fh):
            tmp, sha, _size = _copy_hashed(fh, rfd, MAX_GATE_PDF_BYTES, f)
        final = f"{sha}.pdf"
        os.replace(tmp, final, src_dir_fd=rfd, dst_dir_fd=rfd)
        return final
    finally:
        os.close(rfd)


async def _reject(session: Any, inbox: Path, f: InboxFile, reason: str, send: Send) -> None:
    shown = clean_text(f.path.name, MAX_NAME_CHARS) or "a file"
    move_scanned(inbox, f, "rejected")
    await send(f"Couldn't add {shown} to the GATE bank: {reason}.")
    await session.commit()


async def queue_gate_papers(
    session: Any,
    inbox: Path,
    raw_dir: Path,
    jobs_dir: Path,
    records_dir: Path,
    now: float,
    *,
    send: Send,
    max_files: int = MAX_FILES_PER_RUN,
) -> int:
    """Queue every settled paper-and-key pair under gate/<year>/; returns pairs queued.

    A file with a bad folder, name, year or type goes to `rejected/` with a message. A
    paper whose key has not arrived (or the other way round) waits.
    """
    if not real_subdir(inbox, GATE_DIR):
        return 0
    pairs: dict[tuple[int, str], dict[Role, tuple[InboxFile, GateName]]] = {}
    for f in stable_files(inbox / GATE_DIR, now)[:max_files]:
        parsed = parse_gate_name(f.path.relative_to(inbox / GATE_DIR).parts, now)
        try:
            if isinstance(parsed, str):
                await _reject(session, inbox, f, parsed, send)
                continue
            pairs.setdefault((parsed.year, parsed.paper), {})[parsed.role] = (f, parsed)
        except FileChanged as exc:
            log.info("gate intake skipped %s: %s", clean_text(f.path.name, 80), exc)
            await session.rollback()
        except Exception:
            log.exception("gate intake failed for %s", clean_text(f.path.name, 80))
            await session.rollback()

    queued = 0
    for (year, paper), members in sorted(pairs.items()):
        if len(members) != 2:
            continue  # the other half has not arrived yet
        try:
            if await _queue_pair(
                session, inbox, raw_dir, jobs_dir, records_dir, now, members, send
            ):
                queued += 1
        except FileChanged as exc:
            log.info("gate intake skipped %s %s: %s", paper, year, exc)
            await session.rollback()
        except Exception:
            log.exception("gate intake failed for %s %s", paper, year)
            await session.rollback()
    return queued


async def _queue_pair(
    session: Any,
    inbox: Path,
    raw_dir: Path,
    jobs_dir: Path,
    records_dir: Path,
    now: float,
    members: dict[Role, tuple[InboxFile, GateName]],
    send: Send,
) -> bool:
    for f, _name in members.values():
        reason = _check_pdf(inbox, f)
        if reason is not None:
            await _reject(session, inbox, f, reason, send)
            return False
    paper_f, paper_name = members["paper"]
    key_f, key_name = members["key"]
    paper_raw = _copy_to_raw(inbox, paper_f, raw_dir)
    key_raw = _copy_to_raw(inbox, key_f, raw_dir)
    pair = PyqPair(
        year=paper_name.year,
        paper=paper_name.paper,
        paper_job=uuid.uuid4().hex,
        key_job=uuid.uuid4().hex,
        created=now,
    )
    # The record exists before the jobs, so a result never arrives without one.
    _atomic_write(records_dir, f"{pair.paper_job}.json", pair.model_dump_json())
    write_job(_job(pair.paper_job, paper_raw, paper_name), jobs_dir)
    write_job(_job(pair.key_job, key_raw, key_name), jobs_dir)
    move_scanned(inbox, paper_f, "done")
    move_scanned(inbox, key_f, "done")
    await send(f"Reading {EXAM} {pair.paper} {pair.year} (paper and answer key) for the bank.")
    await session.commit()
    return True


# --- collecting the parsed pair ---------------------------------------------------------


class PyqRow(BaseModel):
    number: Annotated[int, Field(ge=1, le=99)]
    text: Annotated[str, Field(min_length=1, max_length=MAX_QUESTION_CHARS)]
    options: list[Annotated[str, Field(max_length=MAX_OPTION_CHARS)]] | None
    qtype: Literal["MCQ", "MSQ", "NAT"]
    answer_key: Annotated[str, Field(min_length=1, max_length=40)]
    marks: Annotated[float, Field(gt=0, le=10)]


def normalise_key(qtype: str, key: str) -> str | None:
    """The key in its stored form, or None when it is not a valid key of its type."""
    k = " ".join(key.strip().upper().split())
    if qtype == "MCQ":
        return k if _MCQ.fullmatch(k) else None
    if qtype == "MSQ":
        k = k.replace(",", ";").replace(" ", "")
        return ";".join(sorted(set(k.split(";")))) if _MSQ.fullmatch(k) else None
    m = _NAT.fullmatch(k.replace(" TO ", " to "))
    if m is None:
        return None
    low = float(m.group(1))
    if m.group(2) is None:
        return m.group(1)
    if float(m.group(2)) < low:
        return None
    return f"{m.group(1)} to {m.group(2)}"


def build_pyq_rows(paper_text: str, key_text: str) -> tuple[list[PyqRow], int]:
    """Questions that have a valid official key, and how many were left out."""
    keys = parse_answer_key(key_text)
    rows: list[PyqRow] = []
    seen: set[int] = set()
    left_out = 0
    for q in split_questions(paper_text):
        if q.number in seen:
            continue  # the first question with a number wins
        seen.add(q.number)
        entry = keys.get(q.number)
        key = normalise_key(entry.qtype, entry.key) if entry else None
        if entry is None or key is None or not math.isfinite(entry.marks):
            left_out += 1
            continue
        options = [o[:MAX_OPTION_CHARS] for o in q.options[:MAX_OPTIONS]] if q.options else None
        try:
            rows.append(
                PyqRow(
                    number=q.number,
                    text=q.text[:MAX_QUESTION_CHARS],
                    options=options,
                    qtype=entry.qtype,
                    answer_key=key,
                    marks=entry.marks,
                )
            )
        except ValidationError:
            left_out += 1
            continue
        if len(rows) >= MAX_QUESTIONS:
            break
    return rows, left_out


def _read_nofollow(dir_path: Path, name: str, cap: int) -> bytes | None:
    """A regular file's bytes (at most cap), never through a link; None if absent or bad."""
    try:
        dfd = os.open(dir_path, os.O_RDONLY | os.O_DIRECTORY)
    except OSError:
        return None
    try:
        try:
            fd = os.open(name, _NOFOLLOW, dir_fd=dfd)
        except OSError:
            return None
        with os.fdopen(fd, "rb") as fh:
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode) or st.st_size > cap:
                return None
            data = fh.read(cap + 1)
        return data if len(data) <= cap else None
    finally:
        os.close(dfd)


def _result_name(job_id: str) -> str:
    return f"{job_id}.result.json"


def read_result(clean_dir: Path, job_id: str) -> ParseResult | None:
    """The parser's result for job_id; an unreadable or foreign one counts as an error."""
    data = _read_nofollow(clean_dir, _result_name(job_id), MAX_RESULT_BYTES)
    if data is None:
        if os.path.lexists(clean_dir / _result_name(job_id)):
            return ParseResult(job_id=job_id, kind="pdf", status="error", purpose="pyq")
        return None
    try:
        result = ParseResult.model_validate_json(data)
    except ValidationError:
        return ParseResult(job_id=job_id, kind="pdf", status="error", purpose="pyq")
    if result.job_id != job_id or result.purpose != "pyq":
        return ParseResult(job_id=job_id, kind="pdf", status="error", purpose="pyq")
    return result


def _problem(role: Role, result: ParseResult) -> str | None:
    if result.status == "empty":
        return f"the {role} has no text layer (a scanned PDF?)"
    if result.status != "ok" or result.doc is None:
        return f"the {role} could not be read ({result.status})"
    verdict = result.intake.verdict if result.intake else "unchecked"
    if verdict != "pass":
        return f"the intake checks marked the {role} '{verdict}', so it is not used for questions"
    return None


def _cleanup(clean_dir: Path, records_dir: Path, pair: PyqPair) -> None:
    for job_id in (pair.paper_job, pair.key_job):
        with contextlib.suppress(OSError):
            (clean_dir / _result_name(job_id)).unlink()
    with contextlib.suppress(OSError):
        (records_dir / f"{pair.paper_job}.json").unlink()


async def _apply_pair(
    session: AsyncSession, pair: PyqPair, paper: ParseResult, key: ParseResult, send: Send
) -> None:
    label = f"{pair.exam} {pair.paper} {pair.year}"
    problem = _problem("paper", paper) or _problem("key", key)
    if problem is not None:
        await send(f"Couldn't add {label} to the bank: {problem}.")
        return
    assert paper.doc is not None and key.doc is not None  # noqa: S101 (checked above)
    existing = (
        await session.execute(
            select(func.count())
            .select_from(PyqQuestion)
            .where(
                PyqQuestion.exam == pair.exam,
                PyqQuestion.year == pair.year,
                PyqQuestion.paper == pair.paper,
            )
        )
    ).scalar_one()
    if existing:
        await send(f"{label} is already in the bank ({existing} questions).")
        return
    rows, left_out = build_pyq_rows(paper.doc.text, key.doc.text)
    if not rows:
        await send(f"Couldn't add {label} to the bank: no question matched a valid key.")
        return
    for r in rows:
        session.add(
            PyqQuestion(
                exam=pair.exam,
                year=pair.year,
                paper=pair.paper,
                number=r.number,
                text=r.text,
                options=r.options,
                qtype=r.qtype,
                answer_key=r.answer_key,
                marks=r.marks,
                tag_status="none",
            )
        )
    await session.flush()
    note = f" ({left_out} left out: no valid key)" if left_out else ""
    await send(f"{label}: {len(rows)} questions saved to the past-paper bank{note}.")


def _records(records_dir: Path, limit: int) -> list[str]:
    try:
        names = sorted(e.name for e in os.scandir(records_dir) if _RECORD.fullmatch(e.name))
    except OSError:
        return []
    return names[:limit]


async def collect_pyq_results(
    session: AsyncSession,
    records_dir: Path,
    clean_dir: Path,
    now: float,
    *,
    send: Send,
    max_pairs: int = MAX_FILES_PER_RUN,
) -> int:
    """Store every pair whose two results are in; returns the pairs settled.

    The rows and messages are committed before the result files and the record are
    removed. A pair still waiting after a day is given up with a message.
    """
    settled = 0
    for name in _records(records_dir, max_pairs):
        data = _read_nofollow(records_dir, name, MAX_RECORD_BYTES)
        try:
            pair = PyqPair.model_validate_json(data or b"")
        except ValidationError:
            log.warning("pyq record %s is unreadable; removed", name)
            with contextlib.suppress(OSError):
                (records_dir / name).unlink()
            continue
        if name != f"{pair.paper_job}.json":
            continue
        paper = read_result(clean_dir, pair.paper_job)
        key = read_result(clean_dir, pair.key_job)
        try:
            if paper is None or key is None:
                if now - pair.created < PAIR_MAX_AGE_S:
                    continue
                await send(
                    f"Couldn't add {pair.exam} {pair.paper} {pair.year} to the bank: "
                    "the parser did not finish both files."
                )
            else:
                await _apply_pair(session, pair, paper, key, send)
            await session.commit()
        except Exception:
            log.exception("pyq collect failed for %s", name)
            await session.rollback()
            continue
        _cleanup(clean_dir, records_dir, pair)
        settled += 1
    return settled
