"""Secure library file uploads (SEC-57, Decision D48)."""

from __future__ import annotations

import os
from pathlib import Path

# Max upload size: 300MB per Decision D37 & D48
MAX_UPLOAD_SIZE_BYTES: int = 300 * 1024 * 1024

# Allowed file extensions per SEC-57 & Decision D48
ALLOWED_EXTENSIONS: frozenset[str] = frozenset({".pdf", ".docx", ".epub", ".mp4", ".mp3", ".txt"})


class SecurityError(ValueError):
    """Raised when an upload security constraint is violated."""


def sanitize_upload_filename(raw_filename: str) -> str:
    """Sanitize upload filename to prevent path traversal and enforce safe extensions.

    SEC-57 & Decision D48:
    - Strips path traversal attempts (e.g. `../../etc/passwd.pdf` -> `etc_passwd.pdf`).
    - Rejects null bytes and non-printable characters.
    - Enforces safe extensions (.pdf, .docx, .epub, .mp4, .mp3, .txt).
    """
    if not raw_filename or not raw_filename.strip():
        raise ValueError("Filename cannot be empty")

    if "\x00" in raw_filename:
        raise SecurityError("Null bytes are not allowed in filename")

    if not raw_filename.isprintable():
        raise SecurityError("Non-printable characters are not allowed in filename")

    # Normalize backslashes to forward slashes for cross-platform safety
    normalized = raw_filename.replace("\\", "/")

    # Split into parts and strip traversal tokens (. and ..)
    clean_parts: list[str] = []
    for part in normalized.split("/"):
        p = part.strip()
        if not p or all(c == "." for c in p):
            continue
        p = p.lstrip(".")
        if p:
            clean_parts.append(p)

    if not clean_parts:
        raise SecurityError(f"Invalid filename or path traversal attempt: {raw_filename!r}")

    sanitized = "_".join(clean_parts)
    ext = Path(sanitized).suffix.lower()

    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(
            f"Disallowed file extension {ext!r}. Allowed extensions: {sorted(ALLOWED_EXTENSIONS)}"
        )

    # Stem must not be empty (e.g. filename wasn't just '.pdf')
    stem = Path(sanitized).stem.strip()
    if not stem:
        raise ValueError("Filename stem cannot be empty")

    return sanitized


def save_library_upload(raw_filename: str, data: bytes, upload_dir: Path) -> Path:
    """Save raw upload bytes securely into upload_dir with permissions 0o600.

    Enforces:
    - Max size <= 300MB
    - Sanitized filename
    - Destination strictly inside upload_dir
    - Mode 0o600
    """
    if len(data) > MAX_UPLOAD_SIZE_BYTES:
        raise ValueError(
            f"Upload payload size ({len(data)} bytes) exceeds 300MB limit "
            f"({MAX_UPLOAD_SIZE_BYTES} bytes)"
        )

    sanitized_name = sanitize_upload_filename(raw_filename)
    resolved_dir = upload_dir.resolve()
    resolved_dir.mkdir(parents=True, exist_ok=True)

    dest_path = (resolved_dir / sanitized_name).resolve()

    # Enforce destination stays strictly inside resolved_dir
    try:
        dest_path.relative_to(resolved_dir)
    except ValueError as err:
        raise SecurityError(
            f"Path traversal detected: {dest_path} is outside {resolved_dir}"
        ) from err

    if dest_path == resolved_dir:
        raise SecurityError("Destination path cannot be the upload directory itself")

    # Write file safely with 0o600 permissions
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    fd = os.open(dest_path, flags, 0o600)
    try:
        with open(fd, "wb") as f:
            f.write(data)
    finally:
        dest_path.chmod(0o600)

    return dest_path
