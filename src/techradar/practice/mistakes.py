# WIRING(claude): routing quiz, cards; callbacks ans, rate
# WIRING(claude): jobs quiz_job, cards_job, mistakes_page_job
from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import Mistake


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
        q_text = detail.get("question") or detail.get("question_text") or f"Item #{r.ref_id}"
        chosen = (
            detail.get("chosen_text")
            or detail.get("chosen_option")
            or detail.get("chosen_letter")
            or detail.get("chosen_index")
        )
        correct = (
            detail.get("correct_text")
            or detail.get("correct_option")
            or detail.get("correct_letter")
            or detail.get("correct_index")
        )
        explanation = detail.get("explanation", "")

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
        target_file = vault_dir / page_path
        target_file.parent.mkdir(parents=True, exist_ok=True)
        target_file.write_text(md, encoding="utf-8")

    return MistakesResult(
        mistakes_count=len(rows),
        page_path=page_path,
        rendered_bytes=len(md.encode("utf-8")),
        markdown=md,
    )


# --- Backwards compatibility for existing in-memory tests and practice.__init__ ---


class MistakeDict(dict[str, Any]):
    """Dictionary supporting both item and attribute access for mistake fields."""

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError:
            raise AttributeError(f"'MistakeDict' object has no attribute '{name}'") from None

    def __setattr__(self, name: str, value: Any) -> None:
        self[name] = value


class MistakesNotebook:
    """Notebook for tracking incorrect quiz answers and scheduling targeted reviews."""

    def __init__(self) -> None:
        self._mistakes_by_id: dict[str, MistakeDict] = {}
        self._user_mistakes: dict[int, list[str]] = defaultdict(list)

    def record_quiz_mistake(
        self,
        user_id: int,
        question_id: str,
        question_text: str,
        chosen_option: str,
        correct_option: str,
        explanation: str,
    ) -> str:
        mistake_id = f"mstk_{uuid.uuid4().hex[:16]}"
        entry = MistakeDict(
            id=mistake_id,
            user_id=user_id,
            question_id=question_id,
            question_text=question_text,
            chosen_option=str(chosen_option),
            correct_option=str(correct_option),
            explanation=explanation,
            resolved=False,
            created_at=datetime.now(UTC),
            resolved_at=None,
        )
        self._mistakes_by_id[mistake_id] = entry
        self._user_mistakes[user_id].append(mistake_id)
        return mistake_id

    def get_active_mistakes(self, user_id: int) -> list[dict[str, Any]]:
        mistake_ids = self._user_mistakes.get(user_id, [])
        active: list[dict[str, Any]] = []
        for mid in mistake_ids:
            entry = self._mistakes_by_id.get(mid)
            if entry and not entry["resolved"]:
                active.append(dict(entry))
        return active

    def resolve_mistake(self, mistake_id: str) -> None:
        entry = self._mistakes_by_id.get(mistake_id)
        if entry is not None:
            entry["resolved"] = True
            entry["resolved_at"] = datetime.now(UTC)

    def record_mistake(
        self,
        user_id: int,
        question_id: str,
        chosen_option: int | str,
        correct_option: int | str,
        explanation: str,
    ) -> str:
        return self.record_quiz_mistake(
            user_id=user_id,
            question_id=question_id,
            question_text="",
            chosen_option=str(chosen_option),
            correct_option=str(correct_option),
            explanation=explanation,
        )

    def get_mistakes(self, user_id: int) -> list[dict[str, Any]]:
        return self.get_active_mistakes(user_id)
