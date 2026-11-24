"""Monthly capsule: the verified facts of one month, as a generated vault note (Phase 3 Task 8).

SEC: SEC-20, SEC-24, SEC-26.
"""

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
from techradar.pipeline.writer import md_escape, write_note


def _fact_month(f: Any) -> tuple[int, int] | None:
    """The month a fact belongs to: when it is as-of, else when it was first seen."""
    day = getattr(f, "as_of", None) or getattr(f, "first_seen_at", None)
    return (day.year, day.month) if isinstance(day, date) else None


def compose_capsule(month: date, facts: Sequence[Any]) -> str:
    """Verified facts of `month` only, grouped by `SECTION_ORDER`, one bullet each."""
    in_month = [
        f for f in facts if getattr(f, "status", None) == "verified"
        and _fact_month(f) == (month.year, month.month)
    ]  # fmt: skip
    lines = [
        "---",
        "kind: capsule",
        "generated: true",
        f"month: {month.strftime('%Y-%m')}",
        "---",
        f"# Monthly Capsule · {month.strftime('%B %Y')}",
        "",
    ]
    for section in SECTION_ORDER:
        bullets = [f for f in in_month if str(getattr(f, "section", "")).lower() == section.value]
        if not bullets:
            continue
        lines += [f"## {section.value.replace('_', ' ').title()}", ""]
        lines += [f"- {md_escape(str(f.statement))}" for f in bullets]
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def month_start(day: date) -> date:
    """The first day of the month before `day`'s month (the capsule is written on the 1st)."""
    first = day.replace(day=1)
    return date(first.year - 1, 12, 1) if first.month == 1 else first.replace(month=first.month - 1)


async def run_capsule(
    session: AsyncSession,
    vault_root: Path,
    month: date,
    *,
    owner_chat_id: int,
    now: datetime,
) -> str:
    """Write `capsules/<YYYY-MM>.md` from the verified facts of `month` and tell the owner."""
    facts = (await session.execute(select(Fact).where(Fact.status == "verified"))).scalars().all()
    content = compose_capsule(month, facts)
    slug = month.strftime("%Y-%m")
    write_note(vault_root, PurePosixPath("capsules") / f"{slug}.md", content)
    await enqueue_message(
        session,
        chat_id=owner_chat_id,
        text=f"Your {month.strftime('%B')} capsule is in the vault: capsules/{slug}.md",
        purpose="capsule",
    )
    return content
