from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.llm.client import Role, complete_json
from techradar.vault.frontmatter import update_front_matter

GENERATED_START: str = "<!-- generated:start -->"
GENERATED_END: str = "<!-- generated:end -->"


def replace_generated_block(md: str, block: str) -> str:
    """Replace content between generated markers or insert after top heading."""
    clean_block = block.strip()
    if GENERATED_START in md and GENERATED_END in md:
        start_idx = md.find(GENERATED_START) + len(GENERATED_START)
        end_idx = md.find(GENERATED_END)
        return f"{md[:start_idx]}\n{clean_block}\n{md[end_idx:]}"

    # Insert after top heading
    lines = md.splitlines()
    insert_pos = 0
    for idx, line in enumerate(lines):
        if line.startswith("# "):
            insert_pos = idx + 1
            break

    generated_section = f"\n{GENERATED_START}\n{clean_block}\n{GENERATED_END}\n"
    if insert_pos < len(lines):
        lines.insert(insert_pos, generated_section)
        return "\n".join(lines)
    return md + "\n" + generated_section


class FoundationSection(BaseModel):
    model_config = ConfigDict(frozen=True)

    explained: str = Field(max_length=4000)
    key_points: list[str] = Field(max_length=8)
    citations: list[str]


async def queue_background(session: AsyncSession, titles: Sequence[str]) -> int:
    """Queue background fetching and indexing of Wikipedia foundation topics."""
    import hashlib

    from techradar.db.models import RawItem

    queued = 0
    for t in titles:
        url = f"https://en.wikipedia.org/wiki/{t.replace(' ', '_')}"
        url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()
        raw = RawItem(
            source_id=1,
            url=url,
            url_hash=url_hash,
            title=t,
            kind="html",
            status="pending",
        )
        session.add(raw)
        queued += 1
    await session.commit()
    return queued


async def fill_foundation(
    page_path: str,
    deps: Any,
    vault_root: Path,
) -> Literal["updated", "not_enough_sources", "needs_review"]:
    """Retrieve grounded knowledge and update foundation page generated block."""
    full_path = vault_root / page_path
    if not full_path.exists():
        return "not_enough_sources"

    content = full_path.read_text(encoding="utf-8")
    title = full_path.stem.replace("_", " ").title()
    for line in content.splitlines():
        if line.startswith("# "):
            title = line[2:].strip()
            break

    # 1. Retrieve
    hits = await deps.retrieve(title) if hasattr(deps, "retrieve") else getattr(deps, "hits", [])
    usable_hits = [
        h for h in hits if getattr(h, "verified", True) is True or getattr(h, "kind", "") != "news"
    ]

    if len(usable_hits) < 3:
        return "not_enough_sources"

    # 2. Complete section
    try:
        section = await complete_json(
            deps.completer,
            Role.NIGHT,
            "You write a foundation learning section grounded in the retrieved sources. "
            "You must cite excerpts using [C#] tags and list citations accurately.",
            f"Topic: {title}\nSources:\n"
            + "\n".join(
                f"[C{i + 1}] {getattr(h, 'text', str(h))}" for i, h in enumerate(usable_hits)
            ),
            FoundationSection,
        )
    except Exception:
        return "needs_review"

    # 3. Citation check
    valid_citation_ids = {f"C{i + 1}" for i in range(len(usable_hits))}
    for c in section.citations:
        if c not in valid_citation_ids or f"[{c}]" not in section.explained:
            return "needs_review"

    # 4. Render generated block
    kp_lines = "\n".join(f"• {kp}" for kp in section.key_points)
    sources_lines = "\n".join(
        f"• [{c}] {getattr(usable_hits[int(c[1:]) - 1], 'title', 'Source ' + c)}"
        for c in section.citations
    )
    block = f"{section.explained}\n\n### Key Points\n{kp_lines}\n\n## Sources\n{sources_lines}"

    new_content = replace_generated_block(content, block)
    new_content = update_front_matter(new_content, {"filled": date.today().isoformat()})
    full_path.write_text(new_content, encoding="utf-8")
    return "updated"
