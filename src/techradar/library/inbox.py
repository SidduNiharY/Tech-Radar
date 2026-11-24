"""Library inbox intake (Phase 2c Task 2).

Files arrive in `data/library-inbox` (and pack files in `data/library-packs`) through
Syncthing, so their content and names are untrusted. Each settled file is opened once,
without following symlinks at any level (each folder is opened relative to its parent
with O_NOFOLLOW), and must still be the file the scan saw (same inode and size). Type,
size, hash and copy all use that one open file: the hash is computed while copying
into a private temp file, so the stored bytes are exactly the hashed ones, and the copy
stops if the file grows past its limit. The source is removed only if the same inode
is still in place. Moves into `rejected/` and `done/` never overwrite and never follow
links. Each file is handled and committed on its own; one bad file never stops the run.

SEC: SEC-43, SEC-57.
"""

from __future__ import annotations

import contextlib
import errno
import hashlib
import logging
import os
import stat
import unicodedata
import uuid
from collections.abc import Awaitable, Callable, Mapping, Sequence
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import LibraryDoc
from techradar.intake.filetype import DOCX_MIME, EPUB_MIME, ZIP_KINDS, detect_mime_in

LibraryKind = Literal["pdf", "docx", "epub", "video", "audio", "html"]
Origin = Literal["library", "pack"]

MIME_TO_KIND: dict[str, LibraryKind] = {
    "application/pdf": "pdf",
    DOCX_MIME: "docx",
    EPUB_MIME: "epub",
    "video/mp4": "video",
    "video/x-matroska": "video",
    "video/webm": "video",
    "video/quicktime": "video",
    "audio/mpeg": "audio",
    "audio/mp4": "audio",
    "audio/x-m4a": "audio",
    "audio/wav": "audio",
    "audio/x-wav": "audio",
    "audio/ogg": "audio",
    "text/html": "html",
}

# The stored extension comes from the detected type, never from the user's file name.
MIME_TO_EXT: dict[str, str] = {
    "application/pdf": "pdf",
    DOCX_MIME: "docx",
    EPUB_MIME: "epub",
    "video/mp4": "mp4",
    "video/x-matroska": "mkv",
    "video/webm": "webm",
    "video/quicktime": "mov",
    "audio/mpeg": "mp3",
    "audio/mp4": "m4a",
    "audio/x-m4a": "m4a",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/ogg": "ogg",
    "text/html": "html",
}

SKIPPED_DIRS = frozenset({"done", "rejected", "gate"})  # at the inbox root; phase 8 routes gate/
MAX_TITLE_CHARS = 300
MAX_NAME_CHARS = 120
MAX_DEPTH = 8  # folders below the inbox root
MAX_FILES_PER_RUN = 50  # the rest wait for the next run
_HASH_CHUNK = 1024 * 1024
_DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
_FILE_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK

log = logging.getLogger(__name__)


class InboxFile(BaseModel):
    path: Path
    size: int
    mtime: float
    ino: int = 0  # inode and device seen by the scan; the file handled must match
    dev: int = 0


class IntakeDecision(BaseModel):
    kind: LibraryKind | None = None
    reason: str | None = None


class FileChanged(Exception):
    """The file is not the one the scan saw (swapped, grew, became a link): skip it."""


def load_limits(path: Path) -> dict[str, dict[str, int]]:
    """Byte limits per origin and kind (infra/intake/limits.yaml)."""
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {
        origin: {kind: int(n) for kind, n in (kinds or {}).items()}
        for origin, kinds in data.items()
    }


def _skip_name(name: str) -> bool:
    return name.startswith((".", "~syncthing~")) or name.endswith(".tmp")


def stable_files(inbox: Path, now: float, settle_s: int = 60) -> list[InboxFile]:
    """Regular files unchanged for at least `settle_s` seconds, in name order.

    Never follows symlinks (files or folders); walks at most MAX_DEPTH folders deep,
    without recursion. Skips the `done/`, `rejected/` and `gate/` folders at the inbox
    root, dotfiles and dot-folders, `*.tmp` and Syncthing temp files.
    """
    found: list[InboxFile] = []
    stack: list[tuple[Path, int]] = [(inbox, 0)]
    while stack:
        folder, depth = stack.pop()
        try:
            with os.scandir(folder) as it:
                entries = sorted(it, key=lambda e: e.name, reverse=True)
        except OSError:
            continue
        subdirs: list[tuple[Path, int]] = []
        for entry in reversed(entries):
            if _skip_name(entry.name):
                continue
            try:
                if entry.is_symlink():
                    continue
                if entry.is_dir(follow_symlinks=False):
                    skip = depth == 0 and entry.name in SKIPPED_DIRS
                    if not skip and depth < MAX_DEPTH:
                        subdirs.append((Path(entry.path), depth + 1))
                    continue
                if not entry.is_file(follow_symlinks=False):
                    continue
                st = entry.stat(follow_symlinks=False)
            except OSError:
                continue
            if now - st.st_mtime >= settle_s:
                found.append(
                    InboxFile(
                        path=Path(entry.path),
                        size=st.st_size,
                        mtime=st.st_mtime,
                        ino=st.st_ino,
                        dev=st.st_dev,
                    )
                )
        stack.extend(reversed(subdirs))
    return found


def classify(
    f: InboxFile,
    mime: str,
    limits: Mapping[str, Mapping[str, int]],
    origin: Origin,
) -> IntakeDecision:
    """Accept a detected type within its size limit, or say why not."""
    kind = MIME_TO_KIND.get(mime)
    limit = limits.get(origin, {}).get(kind) if kind else None
    if kind is None or limit is None:
        return IntakeDecision(reason=f"unsupported type {mime}")
    if f.size > limit:
        return IntakeDecision(
            reason=f"too large ({f.size // 1_000_000} MB, limit {limit // 1_000_000} MB)"
        )
    return IntakeDecision(kind=kind)


def clean_text(text: str, max_chars: int) -> str:
    """Printable characters only (no control or format characters), whitespace collapsed."""
    kept = "".join(
        " " if ch.isspace() else ch
        for ch in text
        if not unicodedata.category(ch).startswith("C") or ch.isspace()
    )
    return " ".join(kept.split())[:max_chars].strip()


def make_title(name: str) -> str:
    stem = Path(name).stem.replace("_", " ")
    return clean_text(stem, MAX_TITLE_CHARS) or "Untitled"


def _open_parent(inbox: Path, f: InboxFile) -> tuple[int, str]:
    """An fd for the file's folder, opened step by step from the inbox root with
    O_NOFOLLOW, so a folder swapped for a symlink after the scan is refused."""
    parts = f.path.relative_to(inbox).parts
    fd = os.open(inbox, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in parts[:-1]:
            nfd = os.open(part, _DIR_FLAGS, dir_fd=fd)
            os.close(fd)
            fd = nfd
    except OSError as exc:
        os.close(fd)
        raise FileChanged(f"folder changed: {type(exc).__name__}") from exc
    return fd, parts[-1]


def _same(st: os.stat_result, f: InboxFile) -> bool:
    return stat.S_ISREG(st.st_mode) and (st.st_ino, st.st_dev, st.st_size) == (f.ino, f.dev, f.size)


def _unlink_if_same(dir_fd: int, name: str, f: InboxFile) -> None:
    """Remove the source only if the scanned inode is still the one in place."""
    st = os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
    if (st.st_ino, st.st_dev) != (f.ino, f.dev):
        raise FileChanged("replaced before removal")
    os.unlink(name, dir_fd=dir_fd)


def _state_dir_fd(inbox: Path, state: str) -> int:
    """`rejected/` or `done/` under the inbox root; must be a real folder."""
    root = os.open(inbox, os.O_RDONLY | os.O_DIRECTORY)
    try:
        with contextlib.suppress(FileExistsError):
            os.mkdir(state, 0o750, dir_fd=root)
        return os.open(state, _DIR_FLAGS, dir_fd=root)  # a file or symlink here fails
    finally:
        os.close(root)


def _move_to_state(inbox: Path, dir_fd: int, name: str, f: InboxFile, state: str) -> str:
    """Hard-link the file into `rejected/` or `done/` under a free name, then remove
    the source. Never overwrites, never follows a link; returns the name used."""
    sfd = _state_dir_fd(inbox, state)
    try:
        stem, suffix = os.path.splitext(name)
        stem = stem[:150]  # room for a counter within NAME_MAX
        for n in range(1000):
            target = name if n == 0 and len(name) <= 200 else f"{stem}-{n}{suffix[:20]}"
            try:
                os.link(name, target, src_dir_fd=dir_fd, dst_dir_fd=sfd, follow_symlinks=False)
            except FileExistsError:
                continue
            linked = os.stat(target, dir_fd=sfd, follow_symlinks=False)
            if (linked.st_ino, linked.st_dev) != (f.ino, f.dev):
                os.unlink(target, dir_fd=sfd)
                raise FileChanged("replaced while moving")
            _unlink_if_same(dir_fd, name, f)
            return target
        raise OSError(errno.EEXIST, "no free name")
    finally:
        os.close(sfd)


def _copy_hashed(fh, originals_fd: int, limit: int, f: InboxFile) -> tuple[str, str, int]:  # type: ignore[no-untyped-def]
    """Copy the open file into a private temp file while hashing it.

    Returns (temp name, sha256, size). Stops if the file grows past `limit` or
    changes while being copied.
    """
    tmp = f".in-{uuid.uuid4().hex}.part"
    wfd = os.open(
        tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=originals_fd
    )
    h = hashlib.sha256()
    size = 0
    try:
        fh.seek(0)
        while chunk := fh.read(_HASH_CHUNK):
            size += len(chunk)
            if size > limit:
                raise FileChanged("grew past its limit while copying")
            h.update(chunk)
            os.write(wfd, chunk)
        after = os.fstat(fh.fileno())
        if size != f.size or after.st_size != f.size or after.st_mtime != f.mtime:
            raise FileChanged("changed while copying")
        os.fsync(wfd)
        os.fchmod(wfd, 0o440)
    except BaseException:
        os.close(wfd)
        with contextlib.suppress(OSError):
            os.unlink(tmp, dir_fd=originals_fd)
        raise
    os.close(wfd)
    return tmp, h.hexdigest(), size


def _too_large(size: int, limit: int) -> str:
    return f"too large ({size // 1_000_000} MB, limit {limit // 1_000_000} MB)"


async def _take_file(
    session: AsyncSession,
    inbox: Path,
    origin: Origin,
    f: InboxFile,
    library_dir: Path,
    limits: Mapping[str, Mapping[str, int]],
    send: Callable[[str], Awaitable[None]],
) -> int | None:
    """Handle one file; returns the new doc id, or None. Raises FileChanged to skip."""
    shown = clean_text(f.path.name, MAX_NAME_CHARS)
    dir_fd, name = _open_parent(inbox, f)
    try:
        try:
            fd = os.open(name, _FILE_FLAGS, dir_fd=dir_fd)
        except OSError as exc:  # gone, or now a symlink (ELOOP)
            raise FileChanged(f"cannot open: {type(exc).__name__}") from exc
        with os.fdopen(fd, "rb") as fh:
            if not _same(os.fstat(fd), f):
                raise FileChanged("not the scanned file")
            head = fh.read(8)
            origin_limits = limits.get(origin, {})
            zip_limit = max((origin_limits.get(k, 0) for k in ZIP_KINDS), default=0)
            if head.startswith(b"PK\x03\x04") and f.size > zip_limit:
                # Refused before reading the archive's directory (memory).
                decision = IntakeDecision(reason=_too_large(f.size, zip_limit))
                mime = "application/zip"
            else:
                mime = detect_mime_in(fh)
                decision = classify(f, mime, limits, origin)
            if decision.kind is None:
                _move_to_state(inbox, dir_fd, name, f, "rejected")
                await send(f"Couldn't add {shown}: {decision.reason}.")
                return None

            originals = library_dir / "originals"
            originals.mkdir(parents=True, exist_ok=True)
            ofd = os.open(originals, os.O_RDONLY | os.O_DIRECTORY)
            try:
                limit = origin_limits[decision.kind]
                tmp, sha, size = _copy_hashed(fh, ofd, limit, f)
                try:
                    known = (
                        await session.execute(
                            select(LibraryDoc.title).where(LibraryDoc.sha256 == sha)
                        )
                    ).scalar_one_or_none()
                    if known is not None:
                        os.unlink(tmp, dir_fd=ofd)
                        _move_to_state(inbox, dir_fd, name, f, "done")
                        await send(f"Already in your library: {known}.")
                        return None
                    final = f"{sha}.{MIME_TO_EXT[mime]}"
                    os.replace(tmp, final, src_dir_fd=ofd, dst_dir_fd=ofd)
                    os.fsync(ofd)
                except BaseException:
                    with contextlib.suppress(OSError):
                        os.unlink(tmp, dir_fd=ofd)
                    raise
            finally:
                os.close(ofd)

        doc = LibraryDoc(
            sha256=sha,
            title=make_title(f.path.name),
            kind=decision.kind,
            origin=origin,
            original_path=f"originals/{final}",
            size_bytes=size,
            status="queued",
            trust="my_own" if origin == "library" else "open",
        )
        session.add(doc)
        try:
            await session.flush()
        except IntegrityError:
            # Another run stored the same book first; its row points at the same file.
            await session.rollback()
            _move_to_state(inbox, dir_fd, name, f, "done")
            await send(f"Already in your library: {make_title(f.path.name)}.")
            return None
        doc_id = doc.id
        await session.commit()  # the row is durable before the source is removed
        _unlink_if_same(dir_fd, name, f)
        return doc_id
    finally:
        os.close(dir_fd)


async def plan_library_intake(
    session: AsyncSession,
    inboxes: Sequence[tuple[Path, Origin]],
    library_dir: Path,
    now: float,
    limits: Mapping[str, Mapping[str, int]],
    *,
    queue_doc: Callable[[int], Awaitable[None]],
    send: Callable[[str], Awaitable[None]],
    max_files: int = MAX_FILES_PER_RUN,
) -> list[int]:
    """Take settled inbox files into the library; return the new doc ids.

    Each file is handled and committed on its own (its row and messages), and
    `queue_doc(doc_id)` runs only after the commit. A file that fails is logged and
    left for the next run (or, if it changed, skipped); it never stops the run.
    At most `max_files` files are handled per run.
    """
    new_ids: list[int] = []
    handled = 0
    for inbox, origin in inboxes:
        for f in stable_files(inbox, now):
            if handled >= max_files:
                return new_ids
            handled += 1
            try:
                doc_id = await _take_file(session, inbox, origin, f, library_dir, limits, send)
                await session.commit()  # messages for refusals and duplicates
            except FileChanged as exc:
                log.info("library intake skipped %s: %s", clean_text(f.path.name, 80), exc)
                await session.rollback()
                continue
            except Exception:
                log.exception("library intake failed for %s", clean_text(f.path.name, 80))
                await session.rollback()
                continue
            if doc_id is not None:
                new_ids.append(doc_id)
                await queue_doc(doc_id)
    return new_ids
