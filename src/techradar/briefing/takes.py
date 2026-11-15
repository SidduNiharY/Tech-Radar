# WIRING(claude): bot/routing.py needs action take; bot/main.py must pass reply target.

from __future__ import annotations

from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import Take
from techradar.pipeline.writer import md_escape, write_note
from techradar.security.text import sanitize_text

MAX_TAKE_CHARS = 500


def take_rel_path(now: datetime) -> PurePosixPath:
    """Relative path in vault for takes in the given month."""
    return PurePosixPath(f"context/takes/{now.strftime('%Y-%m')}.md")


def format_take_entry(now: datetime, text: str) -> str:
    """Format take entry as a markdown bullet: - <YYYY-MM-DD HH:MM> <md_escaped_text>."""
    timestamp = now.strftime("%Y-%m-%d %H:%M")
    escaped = md_escape(text)
    return f"- {timestamp} {escaped}"


def take_note_entry(now: datetime, text: str) -> tuple[PurePosixPath, str]:
    """Return the relative vault path and formatted take line as data (Section 7.7)."""
    return take_rel_path(now), format_take_entry(now, text)


async def save_take(
    session: AsyncSession,
    vault_root: Path | None,
    briefing_id: int,
    text: str,
    now: datetime,
) -> Literal["saved", "too_long"]:
    """Sanitize and persist a user take on a briefing.

    - Stores a `Take` row in Postgres via the session.
    - If length > MAX_TAKE_CHARS, returns 'too_long' without persisting.
    - If vault_root is provided, appends the take line to context/takes/<YYYY-MM>.md.
    """
    sanitized = sanitize_text(text)
    if len(sanitized) > MAX_TAKE_CHARS:
        return "too_long"

    take_row = Take(briefing_id=briefing_id, text=sanitized, created_at=now)
    session.add(take_row)
    await session.flush()

    if vault_root is not None:
        root = Path(vault_root)
        rel = take_rel_path(now)
        dest = root / Path(rel)
        line = format_take_entry(now, sanitized)
        if dest.is_file() and not dest.is_symlink():
            existing = dest.read_text(encoding="utf-8")
            if existing and not existing.endswith("\n"):
                existing += "\n"
            content = f"{existing}{line}\n"
        else:
            content = f"{line}\n"
        write_note(root, rel, content)

    return "saved"
