"""Held files: the owner's notice, /quarantine list, two-step release and safe delete.

Phase 2c Task 10. SEC: SEC-14, SEC-15, SEC-43, SEC-57.

The release path decides whether a hostile file gets processed, so every step fails closed:

- A release needs two button presses: `qrel:<id>` records the request time, `qrel_ok:<id>`
  must follow within 60 s. Requests live in memory (ReleaseRequests): a restart forgets
  them, which only makes the owner press Release again.
- The release itself claims the row with one conditional UPDATE (`released_at IS NULL AND
  deleted_at IS NULL`), so two confirms, two processes or a stale button can never release
  an item twice.
- A library doc is not gated here: the bot and worker never run the Intake Gateway. Release
  marks the item released, the doc `flagged` and `queued` (its old parts and chapters are
  dropped). The worker then plans its jobs with `ParseJob.owner_released=True` (only because
  a released item exists in the database) and the parser sandbox gates them: a quarantine
  step becomes a flag, a reject stays a reject (the collector marks the doc rejected).
  A doc is released at most once: if it comes back quarantined, the new hold cannot be
  released again.
- Other held files (news, Telegram) cannot be re-run from here: they still go through the
  injected `gate` (Task 10); without one, nothing is released. A gate that still answers
  "quarantined" releases nothing either.
- A released library doc is recorded as `flagged`: searchable, never used for summaries,
  evals, MCQs or cards.
- Delete removes only a regular file inside the quarantine folder: the path is resolved and
  checked, symlinks are refused (never followed), and the unlink goes through a directory
  descriptor opened with O_NOFOLLOW.
"""

from __future__ import annotations

import contextlib
import logging
import os
import re
import stat
import unicodedata
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import Chunk, LibraryChapter, LibraryDoc, LibraryPart, QuarantineItem
from techradar.messaging.outbox import Button, enqueue_message
from techradar.schemas.pipeline import ParseResult

logger = logging.getLogger(__name__)

NOTICE_ORIGINS = frozenset({"telegram", "library", "pack"})
RELEASE_WINDOW = timedelta(seconds=60)
MAX_NAME = 120
MAX_REASONS = 200
LIST_LIMIT = 10

ReleaseGate = Callable[[QuarantineItem], Awaitable[ParseResult]]
ReleaseOutcome = Literal["released", "rejected", "failed", "not_found", "expired", "no_request"]
DeleteOutcome = Literal["deleted", "already", "refused", "not_found"]
FileOutcome = Literal["deleted", "gone", "refused"]

_DROP = frozenset({"Cc", "Cf", "Cs", "Co", "Cn"})
_HELD_NAME = re.compile(r"([0-9a-f]{64})\.[a-z0-9]{1,5}")


# --- text -----------------------------------------------------------------------


def clean_text(value: str, limit: int) -> str:
    """Drop control, format (bidi, zero-width) and unassigned characters; one line, cut."""
    out = []
    for ch in str(value):
        if ch.isspace():
            out.append(" ")
        elif unicodedata.category(ch) not in _DROP:
            out.append(ch)
    return " ".join("".join(out).split())[:limit].strip()


def _reasons_text(reasons: Sequence[str]) -> str:
    parts = [clean_text(r, MAX_REASONS) for r in reasons]
    return clean_text(", ".join(p for p in parts if p), MAX_REASONS) or "no reason given"


def should_notify(origin: str) -> bool:
    """Only files the owner sent (Telegram, library inbox, starter packs) get a notice."""
    return origin in NOTICE_ORIGINS


def render_quarantine_notice(name: str, reasons: Sequence[str]) -> str:
    shown = clean_text(name, MAX_NAME) or "file"
    return (
        f"🔒 Held for review: {shown} ({_reasons_text(reasons)}). "
        "Use /quarantine to release or delete it."
    )


async def notify_quarantined(
    session: AsyncSession, chat_id: int, name: str, reasons: Sequence[str]
) -> int:
    """Queue the held-for-review notice; the caller commits."""
    return await enqueue_message(
        session, chat_id, render_quarantine_notice(name, reasons), purpose="quarantine"
    )


# --- list -----------------------------------------------------------------------


@dataclass(frozen=True)
class QuarantineRow:
    id: int
    name: str
    reasons: list[str]
    expires_at: datetime


def render_quarantine(rows: Sequence[QuarantineRow]) -> tuple[str, list[list[Button]]]:
    """Up to 10 lines `<id>. <name> · <reasons> · deleted on <d MMM>`, one button row each."""
    shown = list(rows)[:LIST_LIMIT]
    if not shown:
        return "Nothing is held for review.", []
    lines = []
    buttons = []
    for r in shown:
        name = clean_text(r.name, MAX_NAME) or "file"
        when = f"{r.expires_at.day} {r.expires_at:%b}"
        lines.append(f"{r.id}. {name} · {_reasons_text(r.reasons)} · deleted on {when}")
        buttons.append(
            [
                Button(text=f"Release {r.id}", data=f"qrel:{r.id}"),
                Button(text=f"Delete {r.id}", data=f"qdel:{r.id}"),
            ]
        )
    return "\n".join(lines), buttons


async def _library_doc(session: AsyncSession, item: QuarantineItem) -> LibraryDoc | None:
    """The library doc a held file belongs to: its name is the original's `<sha256>.<ext>`."""
    if item.origin not in ("library", "pack"):
        return None
    name = Path(item.path).name
    m = _HELD_NAME.fullmatch(name)
    if m is None:
        return None
    doc = (
        await session.execute(select(LibraryDoc).where(LibraryDoc.sha256 == m.group(1)))
    ).scalar_one_or_none()
    if doc is None or Path(doc.original_path).name != name:
        return None
    return doc


async def _display_name(session: AsyncSession, item: QuarantineItem) -> str:
    doc = await _library_doc(session, item)
    return doc.title if doc is not None else Path(item.path).name


async def _live_item(session: AsyncSession, item_id: int) -> QuarantineItem | None:
    """A real item that is neither released nor deleted (fresh from the database)."""
    item = (
        await session.execute(
            select(QuarantineItem)
            .where(
                QuarantineItem.id == item_id,
                QuarantineItem.released_at.is_(None),
                QuarantineItem.deleted_at.is_(None),
            )
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    return item


async def list_quarantine(session: AsyncSession, limit: int = LIST_LIMIT) -> list[QuarantineRow]:
    items = (
        (
            await session.execute(
                select(QuarantineItem)
                .where(QuarantineItem.released_at.is_(None), QuarantineItem.deleted_at.is_(None))
                .order_by(QuarantineItem.created_at.desc(), QuarantineItem.id.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return [
        QuarantineRow(
            id=i.id,
            name=await _display_name(session, i),
            reasons=list(i.reasons),
            expires_at=i.expires_at,
        )
        for i in items
    ]


async def quarantine_listing(session: AsyncSession) -> tuple[str, list[list[Button]]]:
    """The /quarantine reply."""
    return render_quarantine(await list_quarantine(session))


# --- release --------------------------------------------------------------------


class ReleaseRequests:
    """When the owner pressed Release, per item. Each request is used at most once."""

    def __init__(self) -> None:
        self._at: dict[int, datetime] = {}

    def record(self, item_id: int, now: datetime) -> None:
        stale = [k for k, t in self._at.items() if now - t > RELEASE_WINDOW]
        for k in stale:
            del self._at[k]
        self._at[item_id] = now

    def take(self, item_id: int, now: datetime) -> Literal["ok", "expired", "missing"]:
        at = self._at.pop(item_id, None)
        if at is None:
            return "missing"
        if now < at or now - at > RELEASE_WINDOW:
            return "expired"
        return "ok"


async def request_release(
    session: AsyncSession, item_id: int, *, requests: ReleaseRequests, now: datetime
) -> tuple[str, list[list[Button]]] | None:
    """Step 1 (`qrel:<id>`): the confirm prompt, or None for an unknown/used item."""
    item = await _live_item(session, item_id)
    if item is None:
        return None
    requests.record(item.id, now)
    name = clean_text(await _display_name(session, item), MAX_NAME) or "file"
    text = (
        f"Release {name}? It will be processed as flagged: searchable, "
        "but never used for facts, cards or questions."
    )
    return text, [[Button(text="Yes, release", data=f"qrel_ok:{item.id}")]]


async def confirm_release(
    session: AsyncSession,
    item_id: int,
    *,
    requests: ReleaseRequests,
    gate: ReleaseGate | None,
    now: datetime,
) -> ReleaseOutcome:
    """Step 2 (`qrel_ok:<id>`): release only after an unexpired, unused step 1."""
    state = requests.take(item_id, now)
    if state == "missing":
        return "no_request"
    if state == "expired":
        return "expired"
    return await release(session, item_id, gate=gate, now=now)


async def doc_released(
    session: AsyncSession, doc: LibraryDoc, *, exclude: int | None = None
) -> bool:
    """Whether the owner released a held copy of this doc (a released QuarantineItem).

    Held copies are named after the original (`<sha256>.<ext>`), so the item's path ends
    with `/<that name>`.
    """
    name = Path(doc.original_path).name
    stmt = select(QuarantineItem.id).where(
        QuarantineItem.released_at.is_not(None),
        QuarantineItem.origin == doc.origin,
        QuarantineItem.path.endswith(f"/{name}", autoescape=True),
    )
    if exclude is not None:
        stmt = stmt.where(QuarantineItem.id != exclude)
    return (await session.execute(stmt.limit(1))).first() is not None


async def _unclaim(
    session: AsyncSession, item: QuarantineItem, outcome: ReleaseOutcome
) -> ReleaseOutcome:
    item.released_at = None
    await session.flush()
    return outcome


async def _release_library_doc(
    session: AsyncSession, item: QuarantineItem, doc: LibraryDoc
) -> ReleaseOutcome:
    """Mark a held library doc for owner-released reprocessing (see module docstring)."""
    if doc.status != "quarantined":
        return await _unclaim(session, item, "rejected" if doc.status == "rejected" else "failed")
    if await doc_released(session, doc, exclude=item.id):
        # Released once already and held again: never loop through release.
        return await _unclaim(session, item, "rejected")
    await session.execute(delete(LibraryChapter).where(LibraryChapter.doc_id == doc.id))
    await session.execute(delete(LibraryPart).where(LibraryPart.doc_id == doc.id))
    await flag_doc(session, doc)
    doc.status = "queued"
    await session.flush()
    return "released"


async def release(
    session: AsyncSession, item_id: int, *, gate: ReleaseGate | None, now: datetime
) -> ReleaseOutcome:
    """Claim the item atomically, then release it (library doc) or re-gate it (others).

    Flushes only; the caller commits (the claim's row lock holds until then).
    """
    claimed = (
        await session.execute(
            update(QuarantineItem)
            .where(
                QuarantineItem.id == item_id,
                QuarantineItem.released_at.is_(None),
                QuarantineItem.deleted_at.is_(None),
            )
            .values(released_at=now)
            .returning(QuarantineItem.id)
            .execution_options(synchronize_session=False)
        )
    ).scalar_one_or_none()
    if claimed is None:
        return "not_found"
    item = (
        await session.execute(
            select(QuarantineItem)
            .where(QuarantineItem.id == item_id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    doc = await _library_doc(session, item)
    if doc is not None:
        return await _release_library_doc(session, item, doc)
    if gate is None:
        return await _unclaim(session, item, "failed")

    try:
        result = await gate(item)
    except Exception:
        return await _unclaim(session, item, "failed")

    verdict = result.intake.verdict if result.intake is not None else None
    if result.status == "rejected" or verdict == "reject":
        return await _unclaim(session, item, "rejected")
    if result.status != "ok" or verdict not in ("flag", "pass"):
        # Still quarantined (the gate ignored the release), or an error: release nothing.
        return await _unclaim(session, item, "failed")
    await session.flush()
    return "released"


async def flag_doc(session: AsyncSession, doc: LibraryDoc) -> None:
    """Mark a doc flagged and carry it to chunks indexed already (same transaction).

    Never clears a flag. Flushes only; the caller commits.
    """
    if doc.flagged:
        return
    doc.flagged = True
    await session.execute(
        update(Chunk)
        .where(Chunk.doc_kind == "library", Chunk.doc_id == doc.id)
        .values(flagged=True)
        .execution_options(synchronize_session=False)
    )
    await session.flush()


async def doc_flagged(session: AsyncSession, doc_id: int) -> bool:
    value = (
        await session.execute(select(LibraryDoc.flagged).where(LibraryDoc.id == doc_id))
    ).scalar_one_or_none()
    return bool(value)


# --- hold (for the library job collector) ---------------------------------------


_RAW_NAME = re.compile(
    r"[0-9a-f]{64}\.(xml|html|pdf|md|docx|epub|mp4|mkv|webm|mov|mp3|m4a|wav|ogg|png|jpg|jpeg)"
)


def held_file(quarantine_dir: Path, job_id: str) -> Path:
    """The gateway's held copy of a job: the one regular file `<sha256>.<ext>` in
    `quarantine/<job_id>/` (gateway.quarantine_file). The parser can write there, so links
    (the folder or the file) are never followed. Nothing found gives
    `quarantine/<job_id>/missing`, which a delete reports as already gone.
    """
    folder = quarantine_dir / job_id
    fallback = folder / "missing"
    if re.fullmatch(r"[0-9a-f]{32}", job_id) is None:
        return quarantine_dir / "missing"
    try:
        fd = os.open(folder, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except OSError:
        return fallback
    try:
        names = sorted(
            e.name
            for e in os.scandir(fd)
            if _RAW_NAME.fullmatch(e.name) and e.is_file(follow_symlinks=False)
        )
    except OSError:
        return fallback
    finally:
        os.close(fd)
    return folder / names[0] if len(names) == 1 else fallback


async def hold_library_doc(
    session: AsyncSession,
    doc: LibraryDoc,
    *,
    job_id: str,
    quarantine_dir: Path,
    reasons: Sequence[str],
    chat_id: int | None,
) -> QuarantineItem:
    """Record a quarantined library job's held copy and notify the owner, once per job.

    The gateway copied the file to `quarantine_dir/<job_id>/<original name>`.
    """
    existing = (
        await session.execute(select(QuarantineItem).where(QuarantineItem.job_id == job_id))
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    cut = [clean_text(r, 120) for r in reasons][:10]
    item = QuarantineItem(
        job_id=job_id,
        path=str(quarantine_dir / job_id / Path(doc.original_path).name),
        origin=doc.origin,
        reasons=cut,
    )
    session.add(item)
    await session.flush()
    if chat_id is not None and should_notify(doc.origin):
        await notify_quarantined(session, chat_id, doc.title, cut)
    return item


# --- delete ---------------------------------------------------------------------


def remove_held_file(path: Path, quarantine_dir: Path) -> FileOutcome:
    """Delete one regular file inside the quarantine folder; refuse everything else."""
    if not path.is_absolute() or path.name in ("", ".", ".."):
        return "refused"
    try:
        root = quarantine_dir.resolve(strict=True)
    except OSError:
        return "refused"
    try:
        parent = path.parent.resolve(strict=True)
    except FileNotFoundError:
        # Its job folder is gone already (an earlier delete): nothing left to remove.
        inside = path.parent.resolve(strict=False).is_relative_to(root)
        return "gone" if inside else "refused"
    except OSError:
        return "refused"
    if not parent.is_relative_to(root):
        return "refused"
    target = parent / path.name
    if target == root:
        return "refused"
    try:
        fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except OSError:
        return "refused"
    try:
        try:
            st = os.stat(path.name, dir_fd=fd, follow_symlinks=False)
        except FileNotFoundError:
            return "gone"
        if not stat.S_ISREG(st.st_mode):
            return "refused"  # a symlink, folder, fifo or device: never touched
        os.unlink(path.name, dir_fd=fd)
    finally:
        os.close(fd)
    if parent != root:
        with contextlib.suppress(OSError):
            parent.rmdir()  # the job's folder, only when empty
    return "deleted"


def remove_original(library_dir: Path, original_path: str) -> FileOutcome:
    """Delete a library doc's original: only `originals/<sha256>.<ext>`, a regular file.

    The stored path must be exactly that shape (no `..`, no sub-folder); `originals` is
    opened with O_NOFOLLOW and the file is checked with lstat, so no link is followed.
    """
    rel = Path(original_path)
    if rel.is_absolute() or len(rel.parts) != 2 or rel.parts[0] != "originals":
        return "refused"
    name = rel.parts[1]
    if _RAW_NAME.fullmatch(name) is None:
        return "refused"
    try:
        lib_fd = os.open(library_dir, os.O_RDONLY | os.O_DIRECTORY)
    except OSError:
        return "refused"
    try:
        fd = os.open("originals", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=lib_fd)
    except OSError:
        return "refused"
    finally:
        os.close(lib_fd)
    try:
        try:
            st = os.stat(name, dir_fd=fd, follow_symlinks=False)
        except FileNotFoundError:
            return "gone"
        if not stat.S_ISREG(st.st_mode):
            return "refused"
        os.unlink(name, dir_fd=fd)
    except OSError:
        return "refused"
    finally:
        os.close(fd)
    return "deleted"


async def delete_item(
    session: AsyncSession,
    item_id: int,
    *,
    quarantine_dir: Path,
    now: datetime,
    library_dir: Path | None = None,
) -> DeleteOutcome:
    """`qdel:<id>`: delete the held file and mark the row deleted. Flushes only.

    With `library_dir`, a held library doc (still `quarantined`) also loses its original in
    `library/originals` (nothing of it stays to be read again).
    """
    item = (
        await session.execute(
            select(QuarantineItem)
            .where(QuarantineItem.id == item_id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if item is None or item.released_at is not None:
        return "not_found"
    if item.deleted_at is not None:
        return "already"
    if remove_held_file(Path(item.path), quarantine_dir) == "refused":
        return "refused"
    if library_dir is not None:
        doc = await _library_doc(session, item)
        if doc is not None and doc.status == "quarantined":
            gone = remove_original(library_dir, doc.original_path)
            if gone == "refused":
                logger.warning("original of held doc %s was not deleted (refused)", doc.id)
    item.deleted_at = now
    await session.flush()
    return "deleted"
