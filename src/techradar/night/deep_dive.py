from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from techradar.llm.client import Role, complete_json


class ClusterStat(BaseModel):
    model_config = ConfigDict(frozen=True)

    topic: str
    domains: int
    items: int


def pick_topic(
    stats: Sequence[ClusterStat],
    recent_topics: set[str],
) -> str | None:
    """Select the highest-domain topic not covered in recent weeks."""
    eligible = [s for s in stats if s.topic.lower() not in {t.lower() for t in recent_topics}]
    if not eligible:
        return None

    # Sort primarily by domains desc, secondarily by items desc
    sorted_stats = sorted(eligible, key=lambda s: (s.domains, s.items), reverse=True)
    return sorted_stats[0].topic


class DDSection(BaseModel):
    model_config = ConfigDict(frozen=True)

    heading: str = Field(max_length=80)
    body: str = Field(max_length=3000)


class DeepDive(BaseModel):
    model_config = ConfigDict(frozen=True)

    title: str = Field(max_length=120)
    sections: list[DDSection] = Field(min_length=3, max_length=6)
    citations: list[str]


def _slugify(text: str) -> str:
    cleaned = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[-\s]+", "-", cleaned)


async def write_deep_dive(
    topic: str,
    deps: Any,
    vault_root: Path,
    week: str,
) -> Literal["written", "not_enough_sources", "needs_review"]:
    """Generate and write a deeply grounded weekly research report."""
    hits = (
        await deps.retrieve(topic, k_final=10)
        if hasattr(deps, "retrieve")
        else getattr(deps, "hits", [])
    )
    if len(hits) < 3:
        return "not_enough_sources"

    try:
        dd = await complete_json(
            deps.completer,
            Role.NIGHT,
            "You write a weekly deep dive report grounded in the retrieved sources. "
            "Every section must cite excerpts using [C#] tags and list citations accurately.",
            f"Topic: {topic}\nSources:\n"
            + "\n".join(f"[C{i + 1}] {getattr(h, 'text', str(h))}" for i, h in enumerate(hits)),
            DeepDive,
        )
    except Exception:
        return "needs_review"

    # Verify that every section body cites at least one [C#] citation
    citation_pattern = re.compile(r"\[C\d+\]")
    for sec in dd.sections:
        if not citation_pattern.search(sec.body):
            return "needs_review"

    slug = _slugify(dd.title or topic)
    out_dir = vault_root / "deep_dives"
    out_dir.mkdir(parents=True, exist_ok=True)
    file_path = out_dir / f"{week}-{slug}.md"

    body_sections = "\n\n".join(f"## {sec.heading}\n{sec.body}" for sec in dd.sections)
    sources_list = "\n".join(
        f"• [{c}] {getattr(hits[int(c[1:]) - 1], 'title', 'Source ' + c)}"
        for c in dd.citations
        if c.startswith("C") and c[1:].isdigit() and int(c[1:]) <= len(hits)
    )

    doc_text = (
        f"---\n"
        f"week: {week}\n"
        f"topic: {topic}\n"
        f"generated: true\n"
        f"---\n\n"
        f"# {dd.title}\n\n"
        f"{body_sections}\n\n"
        f"## Sources\n{sources_list}\n"
    )
    file_path.write_text(doc_text, encoding="utf-8")

    outbox = getattr(deps, "outbox", None)
    if outbox is not None and hasattr(outbox, "send_text"):
        await outbox.send_text(f"📚 This week's deep dive: {dd.title} (in your vault)")

    return "written"
