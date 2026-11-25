"""Exam files the owner drops into the library inbox (Phase 8 Tasks 2 and 6).

`library-inbox/cutoffs/*.csv` and `library-inbox/weightage/*.csv` are read here, the same
safe way as library/inbox.py reads books: the files arrive through Syncthing, so their
names and bytes are untrusted.

- The scan never follows a link (file or folder). Each settled file is then opened once,
  folder by folder from the inbox root with O_NOFOLLOW, and must still be the file the
  scan saw (same inode, device and size): a file swapped for a link, or for another file,
  between the scan and the open is skipped, never read.
- A file over its size cap is refused from its size alone; it is never read.
- The bytes are read through that one descriptor, at most cap + 1 of them, and must not
  change while being read.
- Handled files move to `rejected/` or `done/` at the inbox root. The move never
  overwrites and never follows a link, and only the scanned inode is moved.
- The database change is committed before the file moves to `done/`, so a crash never
  loses a file that was not stored. Each file is handled on its own; a bad file never
  stops the run.

SEC: SEC-18, SEC-43, SEC-57.
"""

from __future__ import annotations

import contextlib
import logging
import os
import stat
from collections.abc import Awaitable, Callable, Iterator
from pathlib import Path
from typing import Any, BinaryIO, Literal

from pydantic import BaseModel

from techradar.exams.answer_keys import OFFICIAL_DOMAINS, OFFICIAL_SUFFIXES
from techradar.exams.weights import ImportReport, import_cutoff_text, import_weightage_text
from techradar.library.inbox import (
    _FILE_FLAGS,
    MAX_NAME_CHARS,
    FileChanged,
    InboxFile,
    _move_to_state,
    _open_parent,
    _same,
    clean_text,
    stable_files,
)
from techradar.world.econ import load_official_domains

log = logging.getLogger(__name__)

CsvKind = Literal["cutoffs", "weightage"]
CSV_DIRS: tuple[CsvKind, ...] = ("cutoffs", "weightage")
# parse_csv_text refuses more than 1,000,000 characters; UTF-8 text of that length is at
# least this many bytes, so a larger file is refused from its size, unread.
MAX_CSV_BYTES = 1_000_000
MAX_FILES_PER_RUN = 50

Send = Callable[[str], Awaitable[None]]


class CsvOutcome(BaseModel):
    """What storing one file gave: stored (and the message saying so) or the reason not."""

    stored: bool
    message: str


# handle(kind, shown name, text) stores one file's rows (flushed, not committed).
CsvHandler = Callable[[CsvKind, str, str], Awaitable[CsvOutcome]]


def real_subdir(root: Path, name: str) -> bool:
    """True only when root/name is a real folder, not a link (lstat)."""
    try:
        return stat.S_ISDIR(os.lstat(root / name).st_mode)
    except OSError:
        return False


@contextlib.contextmanager
def open_scanned(inbox: Path, f: InboxFile) -> Iterator[tuple[int, str, BinaryIO]]:
    """(parent folder fd, name, open file) for a scanned file; raises FileChanged when the
    file (or a folder on its way) is gone, is a link now, or is not the scanned inode."""
    dir_fd, name = _open_parent(inbox, f)
    try:
        try:
            fd = os.open(name, _FILE_FLAGS, dir_fd=dir_fd)
        except OSError as exc:  # gone, or now a symlink (ELOOP)
            raise FileChanged(f"cannot open: {type(exc).__name__}") from exc
        with os.fdopen(fd, "rb") as fh:
            if not _same(os.fstat(fd), f):
                raise FileChanged("not the scanned file")
            yield dir_fd, name, fh
    finally:
        os.close(dir_fd)


def read_capped(fh: BinaryIO, f: InboxFile, cap: int) -> bytes:
    """All bytes of the open file, which must be the scanned size and stay unchanged."""
    fh.seek(0)
    data = fh.read(cap + 1)
    if len(data) > cap:
        raise FileChanged("grew past its limit while reading")
    after = os.fstat(fh.fileno())
    if len(data) != f.size or after.st_size != f.size or after.st_mtime != f.mtime:
        raise FileChanged("changed while reading")
    return data


def move_scanned(inbox: Path, f: InboxFile, state: Literal["done", "rejected"]) -> str:
    """Move the scanned file into `done/` or `rejected/` at the inbox root."""
    dir_fd, name = _open_parent(inbox, f)
    try:
        return _move_to_state(inbox, dir_fd, name, f, state)
    finally:
        os.close(dir_fd)


def decode_csv(data: bytes) -> str:
    """UTF-8 text (a byte-order mark is dropped); ValueError for anything else."""
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("not UTF-8 text") from exc


def too_large(size: int, cap: int) -> str:
    return f"too large ({size:,} bytes, limit {cap:,})"


async def _take_csv(
    session: Any, inbox: Path, kind: CsvKind, f: InboxFile, handle: CsvHandler, send: Send, cap: int
) -> None:
    shown = clean_text(f.path.name, MAX_NAME_CHARS) or "a file"
    if not f.path.name.lower().endswith(".csv"):
        outcome = CsvOutcome(stored=False, message="only .csv files go in this folder")
    elif f.size > cap:
        outcome = CsvOutcome(stored=False, message=too_large(f.size, cap))  # never read
    else:
        with open_scanned(inbox, f) as (_dir_fd, _name, fh):
            data = read_capped(fh, f, cap)
        try:
            text = decode_csv(data)
        except ValueError as exc:
            outcome = CsvOutcome(stored=False, message=str(exc))
        else:
            outcome = await handle(kind, shown, text)
    if outcome.stored:
        await send(outcome.message)
        await session.commit()  # the rows are durable before the file leaves the inbox
        move_scanned(inbox, f, "done")
        return
    await session.rollback()  # nothing of a refused file is kept
    move_scanned(inbox, f, "rejected")
    await send(f"Couldn't import {shown} ({kind}): {outcome.message}.")
    await session.commit()


async def run_csv_inbox(
    session: Any,
    inbox: Path,
    now: float,
    *,
    handle: CsvHandler,
    send: Send,
    cap: int = MAX_CSV_BYTES,
    max_files: int = MAX_FILES_PER_RUN,
) -> int:
    """Read settled CSV files under `cutoffs/` and `weightage/`; returns the files handled.

    `handle` stores a file's rows; they are committed with the owner's message before the
    file moves to `done/`. A refused file goes to `rejected/` with a message. A file that
    changed is skipped; an error is logged, rolled back and left for the next run.
    """
    handled = 0
    for kind in CSV_DIRS:
        if not real_subdir(inbox, kind):
            continue  # missing, or a link: never scanned
        for f in stable_files(inbox / kind, now):
            if handled >= max_files:
                return handled
            handled += 1
            try:
                await _take_csv(session, inbox, kind, f, handle, send, cap)
            except FileChanged as exc:
                log.info("exam inbox skipped %s: %s", clean_text(f.path.name, 80), exc)
                await session.rollback()
            except Exception:
                log.exception("exam inbox failed for %s", clean_text(f.path.name, 80))
                await session.rollback()
    return handled


def exam_official_domains(path: Path) -> frozenset[str]:
    """Hosts a cutoff's source_url may be on: infra/sources/official_domains.txt, plus the
    exam bodies and the public suffixes of exams/answer_keys.py (`gov.in`, `ac.in`, ...).
    A domain matches itself and its subdomains (weights._is_official_url)."""
    return (
        load_official_domains(path)
        | OFFICIAL_DOMAINS
        | frozenset(s.lstrip(".") for s in OFFICIAL_SUFFIXES)
    )


_REJECTED_WHY = {
    "CsvRejected": "it is too large, has control characters (such as NUL) or is not valid CSV",
    "ValidationError": "a row has a value of the wrong kind",
}


def csv_handler(session: Any, official: frozenset[str]) -> CsvHandler:
    """Store a cutoffs or weightage file with the text functions of exams/weights.py."""

    async def handle(kind: CsvKind, shown: str, text: str) -> CsvOutcome:
        report = ImportReport()
        if kind == "cutoffs":
            await import_cutoff_text(session, shown, text, official, report)
            count, what = report.cutoffs, "cutoffs"
        else:
            await import_weightage_text(session, shown, text, report)
            count, what = report.weights, "topic weights (analysis, unverified)"
        if shown in report.rejected:
            why = _REJECTED_WHY.get(report.rejected[shown], "it could not be stored")
            return CsvOutcome(stored=False, message=why)
        if count == 0:
            need = "an official source_url and a numeric score" if kind == "cutoffs" else "a topic"
            return CsvOutcome(stored=False, message=f"no usable rows (each row needs {need})")
        return CsvOutcome(stored=True, message=f"Imported {count} {what} from {shown}.")

    return handle
