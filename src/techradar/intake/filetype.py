from __future__ import annotations

import contextlib
import urllib.parse
from collections.abc import Mapping

from techradar.schemas.pipeline import IntakeStep, JobKind, ParseJob
from techradar.security.urls import host_allowed, registrable_domain

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
}


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

    # Reject polyglots / executable headers even if labeled as other types
    if head.startswith(b"MZ") or head.startswith(b"\x7fELF") or head.startswith(b"PK\x03\x04"):
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
