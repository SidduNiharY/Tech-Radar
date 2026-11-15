from __future__ import annotations

from datetime import date
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import Reflection

PROMPT_REFLECTION: str = (
    "One conversation this week: what went well, and what would you do differently?"
)


async def save_reflection(
    session: AsyncSession,
    d: date,
    text: str,
    vault_root: Path | None = None,
) -> Path | None:
    """Record weekly English reflection into database and Obsidian vault."""
    row = Reflection(date=d, text=text)
    session.add(row)
    await session.commit()

    if vault_root is not None:
        iso_year, iso_week, _ = d.isocalendar()
        out_dir = vault_root / "reflections"
        out_dir.mkdir(parents=True, exist_ok=True)
        file_path = out_dir / f"{iso_year}-W{iso_week:02d}.md"
        content = (
            f"---\n"
            f"date: {d.isoformat()}\n"
            f"week: {iso_year}-W{iso_week:02d}\n"
            f"type: english-reflection\n"
            f"---\n\n"
            f"# Weekly Reflection - {iso_year}-W{iso_week:02d}\n\n"
            f"**Prompt:** {PROMPT_REFLECTION}\n\n"
            f"{text.strip()}\n"
        )
        file_path.write_text(content, encoding="utf-8")
        return file_path

    return None
