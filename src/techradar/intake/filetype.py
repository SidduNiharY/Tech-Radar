from __future__ import annotations

import contextlib
import urllib.parse
import zipfile
from collections.abc import Mapping
from pathlib import Path

from techradar.schemas.pipeline import IntakeStep, JobKind, ParseJob
from techradar.security.urls import host_allowed, registrable_domain

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
EPUB_MIME = "application/epub+zip"

ALLOWED_MIME: dict[JobKind, frozenset[str]] = {
    "feed": frozenset(
        {
            "application/xml",
            "text/xml",
            "application/rss+xml",
            "application/atom+xml",
        }
    ),
    "page": frozenset({"text/html"}),
    "pdf": frozenset({"application/pdf"}),
    "md": frozenset({"text/plain", "text/markdown"}),
    "docx": frozenset({DOCX_MIME}),
    "epub": frozenset({EPUB_MIME}),
    "video": frozenset({"video/mp4", "video/x-matroska", "video/webm", "video/quicktime"}),
    "audio": frozenset({"audio/mpeg", "audio/mp4", "audio/x-m4a", "audio/wav", "audio/ogg"}),
    "image": frozenset({"image/png", "image/jpeg"}),
}

# Kinds whose files are ZIP archives; only these may start with the ZIP header.
ZIP_KINDS: frozenset[str] = frozenset({"docx", "epub"})
# Zip directories larger than this are not inspected here (check_zip rejects them).
_MAX_ZIP_ENTRIES = 10_000


def detect_mime(head: bytes) -> str:
    """Detect MIME type from file head with fallback heuristics."""
    with contextlib.suppress(Exception):
        import magic

        return magic.from_buffer(head, mime=True)

    # Polyglots / Executables
    if head.startswith(b"MZ"):
        return "application/x-dosexec"
    if head.startswith(b"\x7fELF"):
        return "application/x-executable"
    if head.startswith(b"PK\x03\x04"):
        return "application/zip"

    # Playlists and concat lists: text that makes ffmpeg open other files.
    # Never media, whatever the file is called (checked before any media type).
    stripped = head.lstrip(b"\xef\xbb\xbf \t\r\n")
    if stripped.startswith(b"#EXTM3U"):
        return "application/vnd.apple.mpegurl"
    if stripped.startswith(b"ffconcat"):
        return "text/x-ffconcat"

    media = _media_mime(head)
    if media is not None:
        return media

    # PDF
    if head.startswith(b"%PDF-") or b"%PDF-" in head[:1024]:
        return "application/pdf"

    # HTML
    lower_head = head.lower()
    if b"<html" in lower_head or b"<!doctype html" in lower_head:
        return "text/html"

    # XML / RSS / Atom
    if b"<?xml" in lower_head or b"<rss" in lower_head or b"<feed" in lower_head:
        return "application/xml"

    with contextlib.suppress(Exception):
        import filetype

        kind = filetype.guess(head)
        if kind is not None:
            return kind.mime

    return "text/plain"


def _media_mime(head: bytes) -> str | None:
    """Media and image types from their signatures (no external library)."""
    if len(head) >= 12 and head[4:8] == b"ftyp":
        brand = head[8:12]
        if brand in (b"M4A ", b"M4B "):
            return "audio/mp4"
        if brand == b"qt  ":
            return "video/quicktime"
        return "video/mp4"
    if head.startswith(b"\x1a\x45\xdf\xa3"):  # EBML: Matroska or WebM
        return "video/webm" if b"webm" in head[:64] else "video/x-matroska"
    if head.startswith(b"ID3") or head[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"):
        return "audio/mpeg"
    if head.startswith(b"RIFF") and head[8:12] == b"WAVE":
        return "audio/wav"
    if head.startswith(b"OggS"):
        return "audio/ogg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    return None


def detect_file_mime(path: Path) -> str:
    """detect_mime, plus a look inside ZIP archives to tell DOCX and EPUB apart.

    Only the central directory and the tiny EPUB "mimetype" entry are read;
    check_zip later inspects every entry.
    """
    with path.open("rb") as fh:
        head = fh.read(8192)
    if not head.startswith(b"PK\x03\x04"):
        return detect_mime(head)
    try:
        with zipfile.ZipFile(path) as z:
            infos = z.infolist()
            if len(infos) > _MAX_ZIP_ENTRIES:
                return "application/zip"
            names = {i.filename for i in infos}
            mt = next((i for i in infos if i.filename == "mimetype"), None)
            if (
                mt is not None
                and mt.file_size <= 64
                and z.read(mt).strip() == EPUB_MIME.encode()
                and "META-INF/container.xml" in names
            ):
                return EPUB_MIME
            if "[Content_Types].xml" in names and "word/document.xml" in names:
                return DOCX_MIME
    except zipfile.BadZipFile, OSError, RuntimeError, ValueError:
        pass
    return "application/zip"


def check_source(job: ParseJob, allowed_hosts: frozenset[str]) -> IntakeStep:
    """Validate source origin and domain against allowlists."""
    if job.origin in ("fetch", "pack"):
        parsed = urllib.parse.urlsplit(job.url)
        host = parsed.hostname or ""
        reg_domain = registrable_domain(host)
        if not host or not (
            host_allowed(host, allowed_hosts) or host_allowed(reg_domain, allowed_hosts)
        ):
            return IntakeStep(
                name="source",
                outcome="reject",
                detail=f"Host '{host}' not in allowlist",
            )
        return IntakeStep(name="source", outcome="ok", detail=host)

    if job.origin == "telegram":
        if job.source_id == 0:
            return IntakeStep(name="source", outcome="ok", detail="manual telegram source")
        return IntakeStep(
            name="source",
            outcome="reject",
            detail=f"Invalid telegram source_id {job.source_id}",
        )

    if job.origin in ("library", "upload", "clipping"):
        parsed = urllib.parse.urlsplit(job.url)
        if parsed.scheme == job.origin:
            return IntakeStep(name="source", outcome="ok", detail=f"{job.origin} origin")
        return IntakeStep(
            name="source",
            outcome="reject",
            detail=f"Scheme '{parsed.scheme}' does not match origin '{job.origin}'",
        )

    return IntakeStep(
        name="source",
        outcome="reject",
        detail=f"Unknown origin '{job.origin}'",
    )


def check_size(
    job: ParseJob,
    size: int,
    limits: Mapping[str, Mapping[str, int]],
) -> IntakeStep:
    """Verify raw file size against configured origin/kind limits."""
    origin_limits = limits.get(job.origin, {})
    max_bytes = origin_limits.get(job.kind, 5_000_000)

    if size > max_bytes:
        return IntakeStep(
            name="size",
            outcome="reject",
            detail=f"File size {size} exceeds limit {max_bytes}",
        )
    return IntakeStep(name="size", outcome="ok", detail=f"{size} bytes")


def check_type(job: ParseJob, mime: str, head: bytes) -> IntakeStep:
    """Reject mismatched mime types, missing PDF headers, and polyglot binaries."""
    allowed = ALLOWED_MIME.get(job.kind, frozenset())
    if mime not in allowed:
        return IntakeStep(
            name="type",
            outcome="reject",
            detail=f"Mime '{mime}' not permitted for kind '{job.kind}'",
        )

    # Reject polyglots / executable headers even if labeled as other types.
    # DOCX and EPUB are ZIP archives, so only they may start with the ZIP header.
    zip_head = head.startswith(b"PK\x03\x04") and job.kind not in ZIP_KINDS
    if head.startswith(b"MZ") or head.startswith(b"\x7fELF") or zip_head:
        return IntakeStep(
            name="type",
            outcome="reject",
            detail="Polyglot or executable header detected",
        )

    # PDF must contain %PDF- within first 1024 bytes
    if job.kind == "pdf" and b"%PDF-" not in head[:1024]:
        return IntakeStep(
            name="type",
            outcome="reject",
            detail="Missing '%PDF-' header in first 1024 bytes",
        )

    return IntakeStep(name="type", outcome="ok", detail=mime)
