from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from techradar.llm.client import Role, complete_json


def glossary_candidates(
    entity_counts: Mapping[str, int],
    existing: set[str],
    min_count: int = 3,
) -> list[str]:
    """Filter entity mentions that occur frequently enough to warrant glossary entry."""
    existing_lower = {e.lower() for e in existing}
    candidates: list[tuple[str, int]] = []

    for term, count in entity_counts.items():
        if count >= min_count and term.lower() not in existing_lower:
            candidates.append((term, count))

    # Sort descending by occurrence count
    candidates.sort(key=lambda x: x[1], reverse=True)
    return [c[0] for c in candidates]


class GlossaryEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    term: str = Field(max_length=80)
    definition: str = Field(max_length=500)
    example: str = Field(max_length=200)
    citations: list[str]


def _slugify(text: str) -> str:
    cleaned = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[-\s]+", "-", cleaned)


async def write_glossary_entry(
    term: str,
    deps: Any,
    vault_root: Path,
) -> Path | None:
    """Generate and write a concise, grounded glossary definition."""
    hits = await deps.retrieve(term) if hasattr(deps, "retrieve") else getattr(deps, "hits", [])
    if not hits:
        return None

    entry = await complete_json(
        deps.completer,
        Role.NIGHT,
        "You define a technical or economic concept for a personal knowledge base. "
        "Provide a clear 1-2 sentence definition and an illustrative example.",
        f"Term: {term}\nContext:\n"
        + "\n".join(f"[C{i + 1}] {getattr(h, 'text', str(h))}" for i, h in enumerate(hits)),
        GlossaryEntry,
    )

    slug = _slugify(term)
    out_dir = vault_root / "glossary"
    out_dir.mkdir(parents=True, exist_ok=True)
    file_path = out_dir / f"{slug}.md"

    content = (
        f"---\n"
        f"term: {entry.term}\n"
        f"type: glossary\n"
        f"---\n\n"
        f"# {entry.term}\n\n"
        f"{entry.definition}\n\n"
        f"**Example:** {entry.example}\n"
    )
    file_path.write_text(content, encoding="utf-8")
    return file_path
