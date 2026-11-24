from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import PyqQuestion, SyllabusTopic, UserSettings
from techradar.exams.drills import DrillItem, daily_set
from techradar.pipeline.writer import slugify, write_note
from techradar.rag.answer import answer_question
from techradar.rag.retrieve import RagDeps


class PyqRef(BaseModel):
    model_config = ConfigDict(extra="ignore")

    exam: str
    year: int
    paper: str
    number: int
    text: str = ""
    qtype: str = "MCQ"
    marks: float = 1.0


def final_30(exam_dates: Mapping[str, date], today: date) -> str | None:
    """Find the nearest exam 0-30 days away. None if no dates within 0-30 days."""
    candidates: list[tuple[int, str]] = []
    for exam, exam_date in exam_dates.items():
        days_away = (exam_date - today).days
        if 0 <= days_away <= 30:
            candidates.append((days_away, exam))

    if not candidates:
        return None

    # Pick nearest (smallest days_away), break ties alphabetically
    candidates.sort(key=lambda x: (x[0], x[1]))
    return candidates[0][1]


async def load_pyq_refs(session: AsyncSession, exam: str) -> list[PyqRef]:
    """The real past-paper questions in the bank for one exam (ids come from `pyq_questions`)."""
    rows = (
        (
            await session.execute(
                select(PyqQuestion)
                .where(PyqQuestion.exam == exam)
                .order_by(PyqQuestion.year, PyqQuestion.paper, PyqQuestion.number)
            )
        )
        .scalars()
        .all()
    )
    return [
        PyqRef(
            exam=r.exam,
            year=r.year,
            paper=r.paper,
            number=r.number,
            text=r.text,
            qtype=r.qtype,
            marks=float(r.marks),
        )
        for r in rows
    ]


def mini_mock(exam: str, day: date, pyqs: Sequence[PyqRef] = ()) -> list[DrillItem | PyqRef]:
    """A 20-item mini-mock: bank questions for GATE (`pyqs`), code-made drills otherwise.

    GATE items are picked from the questions given (the caller loads them with
    `load_pyq_refs`), never invented; with fewer than 20 in the bank the mock is shorter.
    The pick depends only on the exam and the day, so Telegram and the web agree.
    """
    if "gate" in exam.lower():
        rng = random.Random(f"{exam}:{day.toordinal()}")  # noqa: S311 - deterministic pick, not crypto
        pool = list(pyqs)
        return list(rng.sample(pool, min(20, len(pool))))

    # Government exams: 10 quant + 10 reasoning drills
    return list(daily_set(day, n_quant=10, n_reasoning=10))


FormulaSheetResult = Literal["written", "not_enough_sources", "needs_review"]


async def write_formula_sheet(
    exam: str,
    subject: str,
    deps: RagDeps,
    vault_root: Path,
) -> FormulaSheetResult:
    """Write `final30/<exam>/<subject-slug>.md` from the owner's own notes, or say why not.

    The text is a grounded answer with code-checked citations (`answer_question`): nothing is
    written when the notes do not cover the subject ("not_enough_sources") or when the answer
    failed a check ("needs_review"). The exam and subject become path parts only as slugs.
    """
    answer = await answer_question(
        f"List the key formulas, identities and definitions of {subject} for {exam}, one per "
        "line, each with its meaning.",
        deps,
    )
    if answer.status == "not_found":
        return "not_enough_sources"
    if answer.status != "answered":
        return "needs_review"

    front = yaml.safe_dump(
        {
            "kind": "formula_sheet",
            "generated": True,
            "exam": exam,
            "subject": subject,
            "citations": sorted({c.doc_path for c in answer.citations}),
        },
        sort_keys=False,
        allow_unicode=True,
    )
    sources = "\n".join(f"- {c.title}" for c in answer.citations)
    content = (
        f"---\n{front}---\n\n# {exam}: {subject}, formula sheet\n\n{answer.text}\n\n"
        f"## Sources\n{sources}\n"
    )
    write_note(vault_root, formula_sheet_rel(exam, subject), content)
    return "written"


def formula_sheet_rel(exam: str, subject: str) -> PurePosixPath:
    """Vault-relative path of one formula sheet; the exam and subject appear only as slugs."""
    return PurePosixPath("final30") / slugify(exam) / f"{slugify(subject)}.md"


def parse_exam_dates(value: object) -> dict[str, date]:
    """`{exam: "YYYY-MM-DD"}` from the owner's settings; anything malformed is skipped."""
    out: dict[str, date] = {}
    if not isinstance(value, dict):
        return out
    for exam, raw in value.items():
        try:
            out[str(exam)] = date.fromisoformat(str(raw))
        except ValueError:
            continue
    return out


async def load_exam_dates(session: AsyncSession) -> dict[str, date]:
    """The exam dates the owner set (`user_settings` key `exam_dates`); empty when none."""
    row = await session.get(UserSettings, "exam_dates")
    return parse_exam_dates(row.value if row else None)


async def run_formula_sheets(
    session: AsyncSession, deps: RagDeps, vault_root: Path, today: date
) -> dict[str, int]:
    """Final-30 night job: a formula sheet per syllabus subject of the nearest exam.

    Does nothing (no error) without an exam date inside 30 days. A sheet that already exists
    is kept. Also refreshes `final30/current-affairs.md`. Returns counts by outcome.
    """
    counts: dict[str, int] = {}
    exam = final_30(await load_exam_dates(session), today)
    if exam is None:
        return counts
    subjects = (
        (
            await session.execute(
                select(SyllabusTopic.subject)
                .where(SyllabusTopic.exam == exam)
                .distinct()
                .order_by(SyllabusTopic.subject)
            )
        )
        .scalars()
        .all()
    )
    for subject in subjects:
        if (vault_root / formula_sheet_rel(exam, subject)).exists():
            counts["kept"] = counts.get("kept", 0) + 1
            continue
        result = await write_formula_sheet(exam, subject, deps, vault_root)
        counts[result] = counts.get(result, 0) + 1
    capsule_bundle(vault_root, today)
    return counts


def capsule_bundle(vault_root: Path, today: date) -> str:
    """Write final30/current-affairs.md linking the last 6 monthly capsules."""
    months: list[str] = []
    for i in range(1, 7):
        total_m = today.year * 12 + (today.month - 1) - i
        y = total_m // 12
        m = (total_m % 12) + 1
        months.append(f"{y:04d}-{m:02d}")

    links = "\n".join(f"- [[capsules/{month}|Capsule {month}]]" for month in months)
    content = f"""# Current Affairs: Last 6 Months Capsule Bundle

Prepared for final 30 days revision sprint.

## Monthly Capsules
{links}
"""
    dest_dir = vault_root / "final30"
    dest_dir.mkdir(parents=True, exist_ok=True)
    out_file = dest_dir / "current-affairs.md"
    out_file.write_text(content, encoding="utf-8")
    return content
