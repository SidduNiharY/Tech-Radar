"""Library inbox intake (Phase 2c Task 2).

Files arrive in `data/library-inbox` (and pack files in `data/library-packs`) through
Syncthing. Each settled file is type-checked and size-checked, hashed, moved to
`library/originals/<sha256>.<ext>` read-only, recorded in `library_docs` and queued for
processing. Nothing here opens a file's content beyond its first bytes (type detection)
and a streamed hash; the user's file name never decides the stored name or extension.

SEC: SEC-43, SEC-57.
"""

from __future__ import annotations

import contextlib
import errno
import hashlib
import os
import shutil
import unicodedata
from collections.abc import Awaitable, Callable, Mapping, Sequence
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import LibraryDoc
from techradar.intake.filetype import DOCX_MIME, EPUB_MIME, detect_file_mime

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
_HASH_CHUNK = 1024 * 1024


class InboxFile(BaseModel):
    path: Path
    size: int
    mtime: float


class IntakeDecision(BaseModel):
    kind: LibraryKind | None = None
    reason: str | None = None


def load_limits(path: Path) -> dict[str, dict[str, int]]:
    """Byte limits per origin and kind (infra/intake/limits.yaml)."""
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {origin: {kind: int(n) for kind, n in kinds.items()} for origin, kinds in data.items()}


def _skip_name(name: str) -> bool:
    return name.startswith((".", "~syncthing~")) or name.endswith(".tmp")


def stable_files(inbox: Path, now: float, settle_s: int = 60) -> list[InboxFile]:
    """Regular files unchanged for at least `settle_s` seconds, in name order.

    Never follows symlinks (files or folders). Skips the `done/`, `rejected/` and `gate/`
    folders at the inbox root, dotfiles and dot-folders, `*.tmp` and Syncthing temp files.
    """
    found: list[InboxFile] = []

    def walk(folder: Path, top: bool) -> None:
        try:
            with os.scandir(folder) as it:
                entries = sorted(it, key=lambda e: e.name)
        except OSError:
            return
        for entry in entries:
            if _skip_name(entry.name):
                continue
            try:
                if entry.is_symlink():
                    continue
                if entry.is_dir(follow_symlinks=False):
                    if not (top and entry.name in SKIPPED_DIRS):
                        walk(Path(entry.path), False)
                    continue
                if not entry.is_file(follow_symlinks=False):
                    continue
                st = entry.stat(follow_symlinks=False)
            except OSError:
                continue
            if now - st.st_mtime >= settle_s:
                found.append(InboxFile(path=Path(entry.path), size=st.st_size, mtime=st.st_mtime))

    walk(inbox, True)
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


def sha256_file(path: Path) -> str:
    """SHA-256 of a file, read in 1 MB chunks."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(_HASH_CHUNK):
            h.update(chunk)
    return h.hexdigest()


def safe_move(src: Path, dest_dir: Path) -> Path:
    """Move `src` into `dest_dir` under its own name, never overwriting: `a.pdf`, `a-1.pdf`, ..."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    stem, suffix = Path(src.name).stem, Path(src.name).suffix
    n = 0
    while True:
        dest = dest_dir / (src.name if n == 0 else f"{stem}-{n}{suffix}")
        n += 1
        try:
            os.link(src, dest)  # fails if dest exists, so nothing is overwritten
        except FileExistsError:
            continue
        except OSError:
            if dest.exists():
                continue
            os.replace(src, dest)
            return dest
        src.unlink()
        return dest


def _fsync_dir(path: Path) -> None:
    with contextlib.suppress(OSError):
        fd = os.open(path, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def store_original(src: Path, library_dir: Path, sha: str, mime: str) -> Path:
    """Move `src` to `library_dir/originals/<sha>.<ext>`, mode 0o440; the ext comes from `mime`."""
    originals = library_dir / "originals"
    originals.mkdir(parents=True, exist_ok=True)
    dest = originals / f"{sha}.{MIME_TO_EXT[mime]}"
    try:
        os.replace(src, dest)
    except OSError as exc:
        if exc.errno != errno.EXDEV:
            raise
        tmp = originals / f".{sha}.part"
        try:
            shutil.copyfile(src, tmp)
            with tmp.open("rb") as fh:
                os.fsync(fh.fileno())
            os.replace(tmp, dest)
        finally:
            tmp.unlink(missing_ok=True)
        src.unlink()
    dest.chmod(0o440)
    _fsync_dir(originals)
    return dest


async def plan_library_intake(
    session: AsyncSession,
    inboxes: Sequence[tuple[Path, Origin]],
    library_dir: Path,
    now: float,
    limits: Mapping[str, Mapping[str, int]],
    *,
    queue_doc: Callable[[int], Awaitable[None]],
    send: Callable[[str], Awaitable[None]],
) -> list[int]:
    """Take every settled inbox file into the library; return the new doc ids.

    The caller commits `session`. `send(text)` posts a message to the owner (the outbox);
    `queue_doc(doc_id)` hands a new doc to the processing queue.
    """
    new_ids: list[int] = []
    for inbox, origin in inboxes:
        for f in stable_files(inbox, now):
            shown = clean_text(f.path.name, MAX_NAME_CHARS)
            try:
                mime = detect_file_mime(f.path)
            except OSError:
                continue  # vanished or unreadable; try again next run
            decision = classify(f, mime, limits, origin)
            if decision.kind is None:
                safe_move(f.path, inbox / "rejected")
                await send(f"Couldn't add {shown}: {decision.reason}.")
                continue

            try:
                sha = sha256_file(f.path)
            except OSError:
                continue
            known = (
                await session.execute(select(LibraryDoc.title).where(LibraryDoc.sha256 == sha))
            ).scalar_one_or_none()
            if known is not None:
                safe_move(f.path, inbox / "done")
                await send(f"Already in your library: {known}.")
                continue

            stored = store_original(f.path, library_dir, sha, mime)
            doc = LibraryDoc(
                sha256=sha,
                title=make_title(f.path.name),
                kind=decision.kind,
                origin=origin,
                original_path=stored.relative_to(library_dir).as_posix(),
                size_bytes=stored.stat().st_size,
                status="queued",
                trust="my_own" if origin == "library" else "open",
            )
            session.add(doc)
            await session.flush()
            new_ids.append(doc.id)
            await queue_doc(doc.id)
    return new_ids
