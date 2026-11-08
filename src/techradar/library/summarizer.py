from __future__ import annotations

import os
import re
from collections.abc import Sequence
from datetime import UTC, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml
from pydantic import BaseModel, Field

from techradar.library.models import Chapter


class ChapterSummary(BaseModel):
    """Structured summary of a chapter with code-checked citations."""

    chapter_id: str
    title: str
    summary_markdown: str
    key_ideas: list[str] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)


def is_night_window(now_dt: datetime, tz_name: str = "Asia/Kolkata") -> bool:
    """Return True only if local time is between 01:00 and 05:00 in given timezone."""
    tz = ZoneInfo(tz_name)
    if now_dt.tzinfo is None:
        local_dt = now_dt.replace(tzinfo=tz)
    else:
        local_dt = now_dt.astimezone(tz)

    t = local_dt.time()
    return time(1, 0) <= t < time(5, 0)


def check_key_idea_citations(key_ideas: Sequence[str]) -> bool:
    """Verify that every key idea contains at least one [C#] citation marker."""
    return all(bool(re.search(r"\[C[0-9]+\]", idea)) for idea in key_ideas)


def render_chapter_vault_note(
    chapter: Chapter,
    summary: ChapterSummary,
    book_slug: str,
    vault_dir: Path,
) -> Path:
    """Write chapter summary note to vault with frontmatter, citations, and SEC-24 path validation.

    Destination: <vault_dir>/Library/<book_slug>/<chapter.slug>.md
    """
    if not book_slug or not chapter.slug:
        raise ValueError("book_slug and chapter.slug must not be empty")

    # Enforce safe relative paths (SEC-24)
    rel = Path("Library") / book_slug / f"{chapter.slug}.md"
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError(f"Path traversal detected in relative path: {rel}")

    # Symlink traversal protection
    curr = vault_dir
    for part in rel.parts:
        curr = curr / part
        if curr.is_symlink():
            raise ValueError(f"Refusing to write through symlink: {curr}")

    resolved_vault = vault_dir.resolve()
    dest = (vault_dir / rel).resolve()

    try:
        dest.relative_to(resolved_vault)
    except ValueError as exc:
        raise ValueError(f"Path traversal detected: {dest} outside {resolved_vault}") from exc

    # Verify that key ideas carry code-checked [C#] citation markers
    if summary.key_ideas and not check_key_idea_citations(summary.key_ideas):
        raise ValueError("All key ideas must contain code-checked citation markers [C#]")

    frontmatter = {
        "title": summary.title or chapter.title,
        "book_slug": book_slug,
        "chapter_ordinal": chapter.ordinal,
        "created_at": datetime.now(UTC).isoformat(),
        "status": "ready",
    }

    body_lines: list[str] = [
        "---",
        yaml.dump(frontmatter, sort_keys=False).strip(),
        "---",
        "",
        f"# {summary.title or chapter.title}",
        "",
        "## Summary",
        "",
        summary.summary_markdown.strip(),
        "",
    ]

    if summary.key_ideas:
        body_lines.append("## Key Ideas")
        body_lines.append("")
        for idea in summary.key_ideas:
            body_lines.append(f"- {idea}")
        body_lines.append("")

    if summary.citations:
        body_lines.append("## Citations")
        body_lines.append("")
        for cit in summary.citations:
            marker = cit if cit.startswith("[") else f"[{cit}]"
            body_lines.append(f"- {marker}")
        body_lines.append("")

    content = "\n".join(body_lines).rstrip() + "\n"

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = dest.with_name(f"{dest.name}.tmp")
    tmp_path.write_text(content, encoding="utf-8")
    os.replace(tmp_path, dest)

    return dest
