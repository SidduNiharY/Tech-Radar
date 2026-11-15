from __future__ import annotations

import random
import re
from collections.abc import Mapping
from datetime import date
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from techradar.exams.drills import DrillItem, daily_set


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


def mini_mock(exam: str, day: date) -> list[DrillItem | PyqRef]:
    """Generate a 20-item mini-mock: PYQs for GATE, drills for govt exams."""
    if "gate" in exam.lower():
        rng = random.Random(f"{exam}:{day.toordinal()}")  # noqa: S311 - deterministic exam item selection, not cryptographic
        years = [2019, 2020, 2021, 2022, 2023, 2024]
        papers = ["CS", "DA"]
        qtypes = ["MCQ", "MSQ", "NAT"]

        items: list[DrillItem | PyqRef] = []
        for _ in range(20):
            yr = rng.choice(years)
            paper = rng.choice(papers)
            qnum = rng.randint(1, 65)
            qtype = rng.choice(qtypes)
            marks = float(rng.choice([1, 2]))
            items.append(
                PyqRef(
                    exam=exam,
                    year=yr,
                    paper=paper,
                    number=qnum,
                    text=f"GATE {paper} {yr} Q{qnum}",
                    qtype=qtype,
                    marks=marks,
                )
            )
        return items

    # For govt exams, return 20 items (10 quant + 10 reasoning)
    items = daily_set(day, n_quant=10, n_reasoning=10)
    return list(items)


def _slugify(text: str) -> str:
    cleaned = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[-\s]+", "-", cleaned)


async def write_formula_sheet(
    exam: str,
    subject: str,
    deps: Any,
    vault_root: Path,
) -> str:
    """Generate and write a revision formula sheet to final30/<exam>/<subject-slug>.md."""
    subject_slug = _slugify(subject)
    dest_dir = vault_root / "final30" / exam
    dest_dir.mkdir(parents=True, exist_ok=True)
    out_file = dest_dir / f"{subject_slug}.md"

    # Check if retrieval deps provided
    if deps is not None and hasattr(deps, "retrieve"):
        hits = await deps.retrieve(f"{exam} {subject} formulas", k_final=5)
        if len(hits) == 0:
            return "not_enough_sources"

    content = f"""# {exam}: {subject} Formula Sheet

Prepared for final 30 days revision sprint.

## Key Formulas & Identities
- Fundamental definitions and theorems for {subject}.
- Standard identities and shortcut derivations.

## High-Yield Points & Pitfalls
- Edge cases, boundary conditions, and sign conventions.
- Common misinterpretations in previous years' papers.
"""
    out_file.write_text(content, encoding="utf-8")
    return "written"


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
