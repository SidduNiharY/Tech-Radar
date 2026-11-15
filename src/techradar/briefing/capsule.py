from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.briefing.compose import SECTION_ORDER
from techradar.db.models import Fact
from techradar.messaging.outbox import enqueue_message
from techradar.pipeline.writer import write_note


def _get_fact_month(f: Any) -> tuple[int, int] | None:
    dt = getattr(f, "as_of", None) or getattr(f, "first_seen_at", None)
    if dt is None:
        return None
    if isinstance(dt, datetime):
        return dt.year, dt.month
    if isinstance(dt, date):
        return dt.year, dt.month
    return None


def _is_fact_verified(f: Any) -> bool:
    status = getattr(f, "status", None)
    if status is not None:
        return status == "verified"
    return bool(getattr(f, "verified", False))


def compose_capsule(month: date, facts: Sequence[Any]) -> str:
    """Compose a monthly capsule note from verified facts of that month."""
    target_ym = (month.year, month.month)
    verified_facts = [
        f
        for f in facts
        if _is_fact_verified(f) and (_get_fact_month(f) == target_ym or _get_fact_month(f) is None)
    ]

    # Map section order to canonical strings
    canonical_sections = [s.value if hasattr(s, "value") else str(s).lower() for s in SECTION_ORDER]

    facts_by_section: dict[str, list[Any]] = {s: [] for s in canonical_sections}
    for f in verified_facts:
        sec = getattr(f, "section", "")
        sec_str = sec.value if hasattr(sec, "value") else str(sec).lower()
        if sec_str in facts_by_section:
            facts_by_section[sec_str].append(f)
        else:
            facts_by_section.setdefault(sec_str, []).append(f)

    month_str = month.strftime("%Y-%m")
    lines = [
        "---",
        "kind: capsule",
        "generated: true",
        f"month: {month_str}",
        "---",
        f"# Monthly Capsule · {month.strftime('%B %Y')}",
        "",
    ]

    for sec in canonical_sections:
        sec_facts = facts_by_section.get(sec, [])
        if not sec_facts:
            continue
        lines.append(f"## {sec.replace('_', ' ').title()}")
        lines.append("")
        for f in sec_facts:
            stmt = getattr(f, "statement", str(f))
            lines.append(f"- {stmt}")
        lines.append("")

    return "\n".join(lines).strip() + "\n"


async def run_capsule(session: AsyncSession, vault_root: Path, month: date) -> str:
    """Queries verified facts, writes the monthly capsule note, and enqueues notification."""
    stmt = select(Fact).where(Fact.status == "verified")
    res = await session.execute(stmt)
    facts = res.scalars().all()

    content = compose_capsule(month, facts)
    month_slug = month.strftime("%Y-%m")
    rel_path = PurePosixPath("capsules") / f"{month_slug}.md"
    write_note(vault_root, rel_path, content)

    month_name = month.strftime("%B")
    msg = f"Your {month_name} capsule is in the vault: capsules/{month_slug}.md"
    await enqueue_message(session, msg)
    return content
