from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import Mistake
from techradar.pipeline.writer import md_escape, write_note


class MistakeRow(BaseModel):
    id: int
    kind: str
    ref_id: int
    detail: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


def render_mistakes_page(rows: Sequence[MistakeRow]) -> str:
    """Renders the mistakes notebook vault page practice/mistakes.md."""
    front_matter = [
        "---",
        "kind: mistakes",
        "generated: true",
        f"total: {len(rows)}",
        "---",
        "",
        "# Mistakes Notebook",
        "",
        "This notebook records incorrect quiz questions and drill mistakes for spaced review.",
        "",
    ]
    if not rows:
        front_matter.append("No recorded mistakes. Keep practicing!")
        return "\n".join(front_matter) + "\n"

    sections: list[str] = []
    for r in rows:
        ts = r.created_at.strftime("%Y-%m-%d %H:%M")
        kind_label = r.kind.upper()
        detail = r.detail or {}
        q_text = md_escape(
            str(detail.get("question") or detail.get("question_text") or f"Item #{r.ref_id}")
        )
        chosen = md_escape(
            str(
                detail.get("chosen_text")
                or detail.get("chosen_option")
                or detail.get("chosen_letter")
                or detail.get("chosen_index")
            )
        )
        correct = md_escape(
            str(
                detail.get("correct_text")
                or detail.get("correct_option")
                or detail.get("correct_letter")
                or detail.get("correct_index")
            )
        )
        explanation = md_escape(str(detail.get("explanation", "")))

        entry_lines = [
            f"### [{kind_label}] #{r.ref_id} · {ts}",
            "",
            f"**Question:** {q_text}",
            "",
            f"- **Your Answer:** {chosen}",
            f"- **Correct Answer:** {correct}",
        ]
        if explanation:
            entry_lines.extend(["", f"**Explanation:** {explanation}"])
        entry_lines.append("")
        sections.append("\n".join(entry_lines))

    return "\n".join(front_matter) + "\n" + "\n---\n\n".join(sections)


class MistakesResult(BaseModel):
    mistakes_count: int = 0
    page_path: str = "practice/mistakes.md"
    rendered_bytes: int = 0
    markdown: str = ""


async def run_mistakes_page(
    session: AsyncSession,
    *,
    now: datetime,
    vault_dir: Path | None = None,
) -> MistakesResult:
    """Job body for mistakes_page_job. Queries mistakes and updates vault page."""
    stmt = select(Mistake).order_by(Mistake.created_at.desc())
    res = await session.execute(stmt)
    mistakes = list(res.scalars().all())

    rows = [
        MistakeRow(
            id=m.id,
            kind=m.kind,
            ref_id=m.ref_id,
            detail=m.detail,
            created_at=m.created_at,
        )
        for m in mistakes
    ]

    md = render_mistakes_page(rows)
    page_path = "practice/mistakes.md"

    if vault_dir is not None:
        write_note(vault_dir, PurePosixPath(page_path), md)

    return MistakesResult(
        mistakes_count=len(rows),
        page_path=page_path,
        rendered_bytes=len(md.encode("utf-8")),
        markdown=md,
    )
