from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict


class TimelineEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    date: date
    title: str
    note_path: str


def timeline_entries(
    clusters: Sequence[Any],
    entity: str,
) -> list[TimelineEntry]:
    """Extract and chronologically sort news cluster events related to an entity."""
    ent_lower = entity.lower()
    entries: list[TimelineEntry] = []

    for c in clusters:
        cluster_entities = [e.lower() for e in getattr(c, "entities", [])]
        if ent_lower in cluster_entities:
            entries.append(
                TimelineEntry(
                    date=getattr(c, "date", date.today()),
                    title=getattr(c, "title", "Event"),
                    note_path=getattr(c, "note_path", ""),
                )
            )

    entries.sort(key=lambda x: x.date)
    return entries


def _slugify(text: str) -> str:
    cleaned = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[-\s]+", "-", cleaned)


def render_timeline(entity: str, entries: Sequence[TimelineEntry]) -> str:
    """Format an entity timeline in clean Obsidian markdown."""
    lines: list[str] = [
        "---",
        f"entity: {entity}",
        "type: timeline",
        "---",
        "",
        f"# Timeline: {entity}",
        "",
    ]
    for e in entries:
        link_str = f"[[{e.note_path}|{e.title}]]" if e.note_path else e.title
        lines.append(f"- **{e.date.isoformat()}**: {link_str}")

    return "\n".join(lines)


def write_timeline(
    entity: str,
    entries: Sequence[TimelineEntry],
    vault_root: Path,
) -> Path:
    """Write regenerated entity timeline to the vault."""
    slug = _slugify(entity)
    out_dir = vault_root / "timelines"
    out_dir.mkdir(parents=True, exist_ok=True)
    file_path = out_dir / f"{slug}.md"
    file_path.write_text(render_timeline(entity, entries), encoding="utf-8")
    return file_path
