"""Private, no-follow writes and reads of files the owner sends through Telegram.

Phase 3 Task 3 (PDFs and pasted text) and Phase 6 Task 1 (voice notes). A file is always named
`<sha256>.<ext>`: the hash of its bytes and an extension from the checked type, never the name
Telegram reports. Writes go to a private temp file (O_CREAT | O_EXCL | O_NOFOLLOW, mode 0o640)
inside a folder opened with O_NOFOLLOW, then are hard-linked into place, so nothing is ever
written through a planted symlink and an existing name is never overwritten. Reads open the
file relative to its folder with O_NOFOLLOW, require a regular file with one link, cap the
size, and check that the bytes still hash to the name.

SEC: SEC-15, SEC-57.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import re
import stat
import uuid
from pathlib import Path
from typing import Literal

OwnerExt = Literal["pdf", "html", "ogg"]
EXTS: frozenset[str] = frozenset({"pdf", "html", "ogg"})
NAME_RE = re.compile(r"[0-9a-f]{64}\.(?:pdf|html|ogg)")
FILE_MODE = 0o640

_DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
_READ_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
_CHUNK = 1024 * 1024


class UnsafeFile(Exception):
    """The file or its folder is not what it must be (a link, too large, swapped)."""


def _open_dir(folder: Path, *, create: bool) -> int:
    try:
        if create:
            folder.mkdir(parents=True, exist_ok=True)
        return os.open(folder, _DIR_FLAGS)
    except OSError as exc:
        raise UnsafeFile(f"folder is not a real folder: {type(exc).__name__}") from exc


def write_private(folder: Path, data: bytes, ext: OwnerExt) -> str:
    """Store `data` as `<sha256>.<ext>` in `folder`; return the name.

    The same bytes twice give the same file. A different file (or a link) already at that name
    raises UnsafeFile; nothing is followed or overwritten.
    """
    if ext not in EXTS:
        raise ValueError(f"unknown extension {ext!r}")
    name = f"{hashlib.sha256(data).hexdigest()}.{ext}"
    dfd = _open_dir(folder, create=True)
    try:
        tmp = f".{uuid.uuid4().hex}.part"
        fd = os.open(
            tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, FILE_MODE, dir_fd=dfd
        )
        try:
            try:
                view = memoryview(data)
                while view:
                    view = view[os.write(fd, view) :]
                os.fchmod(fd, FILE_MODE)  # the umask never widens or narrows it
                os.fsync(fd)
            finally:
                os.close(fd)
            try:
                os.link(tmp, name, src_dir_fd=dfd, dst_dir_fd=dfd, follow_symlinks=False)
            except FileExistsError:
                st = os.stat(name, dir_fd=dfd, follow_symlinks=False)
                if not stat.S_ISREG(st.st_mode) or st.st_size != len(data):
                    raise UnsafeFile("another file already has that name") from None
        finally:
            with contextlib.suppress(OSError):
                os.unlink(tmp, dir_fd=dfd)
        return name
    finally:
        os.close(dfd)


def read_private(folder: Path, name: str, max_bytes: int) -> tuple[bytes, os.stat_result]:
    """The bytes of `folder/name` and the stat of the file read.

    `name` must be a hash name (`<sha256>.<ext>`): a path, another extension or upper case is
    refused before anything is opened. The file must be a regular file with one link, at most
    `max_bytes`, and its bytes must hash to its name.
    """
    if not NAME_RE.fullmatch(name):
        raise UnsafeFile("not a hash name")
    dfd = _open_dir(folder, create=False)
    try:
        try:
            fd = os.open(name, _READ_FLAGS, dir_fd=dfd)
        except OSError as exc:  # missing, or a symlink (ELOOP)
            raise UnsafeFile(f"cannot open: {type(exc).__name__}") from exc
        with os.fdopen(fd, "rb") as fh:
            st = os.fstat(fh.fileno())
            if not stat.S_ISREG(st.st_mode):
                raise UnsafeFile("not a regular file")
            if st.st_nlink != 1:
                raise UnsafeFile("file has other links")
            if st.st_size > max_bytes:
                raise UnsafeFile("too large")
            chunks: list[bytes] = []
            size = 0
            while chunk := fh.read(_CHUNK):
                size += len(chunk)
                if size > max_bytes:
                    raise UnsafeFile("grew past its limit")
                chunks.append(chunk)
        data = b"".join(chunks)
        if hashlib.sha256(data).hexdigest() != name.split(".", 1)[0]:
            raise UnsafeFile("content does not match its name")
        return data, st
    finally:
        os.close(dfd)


def remove_if_same(folder: Path, name: str, st: os.stat_result) -> None:
    """Unlink `folder/name` only if it is still the inode that was read."""
    if not NAME_RE.fullmatch(name):
        raise UnsafeFile("not a hash name")
    dfd = _open_dir(folder, create=False)
    try:
        try:
            now = os.stat(name, dir_fd=dfd, follow_symlinks=False)
        except FileNotFoundError:
            return
        if (now.st_ino, now.st_dev) == (st.st_ino, st.st_dev):
            os.unlink(name, dir_fd=dfd)
    finally:
        os.close(dfd)
