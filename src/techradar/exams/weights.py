from __future__ import annotations

import csv
import io
import math
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import Cutoff
from techradar.db.models import TopicWeight as TopicWeightRow


class CutoffRow(BaseModel):
    model_config = ConfigDict(extra="ignore")

    exam: str = Field(min_length=1)
    year: int
    tier: str = Field(min_length=1)
    category: str = Field(min_length=1)
    score: float = Field(ge=0.0)
    source_url: str = Field(min_length=1)


class WeightRow(BaseModel):
    model_config = ConfigDict(extra="ignore")

    exam: str
    subject: str
    topic: str
    questions: int = 0
    year: int | None = None
    source_url: str = ""
    source: str = "analysis"


class TopicWeight(BaseModel):
    subject: str
    topic: str
    marks_total: float
    share: float
    # Set for imported weightage (stored in `topic_weights`); GATE weights leave them empty.
    exam: str = ""
    weight: float = 0.0
    source: str = ""


class PyqRow(BaseModel):
    model_config = ConfigDict(extra="ignore")

    subject: str = "General"
    topic: str
    marks: float = 1.0


def _is_official_url(url: str, official: frozenset[str]) -> bool:
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").strip().lower()
        if not host:
            return False
        return any(host == d or host.endswith("." + d) for d in official)
    except Exception:
        return False


def import_cutoffs(
    rows: Iterable[dict[str, Any]],
    official: frozenset[str],
) -> list[CutoffRow]:
    """Import cutoffs from CSV rows, rejecting non-official sources and invalid scores."""
    out: list[CutoffRow] = []
    for r in rows:
        url = str(r.get("source_url", "")).strip()
        if not _is_official_url(url, official):
            continue

        raw_score = r.get("score")
        if raw_score is None:
            continue
        try:
            score = float(raw_score)
            if score < 0.0 or math.isnan(score) or math.isinf(score):
                continue
        except ValueError, TypeError:
            continue

        raw_year = r.get("year")
        try:
            year = int(raw_year) if raw_year is not None else 0
        except ValueError, TypeError:
            continue

        exam = str(r.get("exam", "")).strip()
        tier = str(r.get("tier", "")).strip()
        category = str(r.get("category", "")).strip()
        if not exam or not tier or not category:
            continue

        out.append(
            CutoffRow(
                exam=exam,
                year=year,
                tier=tier,
                category=category,
                score=score,
                source_url=url,
            )
        )
    return out


def import_weightage(rows: Iterable[dict[str, Any]]) -> list[WeightRow]:
    """Import weightage CSV rows with source='analysis'."""
    out: list[WeightRow] = []
    for r in rows:
        exam = str(r.get("exam", "")).strip()
        subject = str(r.get("subject", "")).strip()
        topic = str(r.get("topic", "")).strip()
        if not topic:
            continue

        raw_q = r.get("questions", 0)
        try:
            questions = int(raw_q)
        except ValueError, TypeError:
            questions = 0

        raw_y = r.get("year")
        year: int | None = None
        if raw_y is not None:
            try:
                year = int(raw_y)
            except ValueError, TypeError:
                year = None

        source_url = str(r.get("source_url", "")).strip()

        out.append(
            WeightRow(
                exam=exam,
                subject=subject,
                topic=topic,
                questions=questions,
                year=year,
                source_url=source_url,
                source="analysis",
            )
        )
    return out


MAX_CSV_BYTES = 1_000_000
MAX_CSV_ROWS = 5000
UNVERIFIED = "analysis (unverified)"


def read_csv_rows(folder: Path) -> list[dict[str, Any]]:
    """Rows of every regular `*.csv` in one inbox folder (the owner's own files).

    A link, a file over 1 MB, or a folder that is not there contributes nothing; at most
    5,000 rows are read in all. The text is data: it is only parsed, never run.
    """
    rows: list[dict[str, Any]] = []
    if not folder.is_dir() or folder.is_symlink():
        return rows
    for path in sorted(folder.glob("*.csv")):
        try:
            if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_CSV_BYTES:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for row in csv.DictReader(io.StringIO(text)):
            rows.append(dict(row))
            if len(rows) >= MAX_CSV_ROWS:
                return rows
    return rows


def aggregate_weightage(rows: Iterable[WeightRow]) -> list[TopicWeight]:
    """One weight per (exam, subject, topic): the questions summed over the years given."""
    totals: dict[tuple[str, str, str], float] = {}
    for r in rows:
        key = (r.exam, r.subject, r.topic)
        totals[key] = totals.get(key, 0.0) + float(r.questions)
    grand = sum(totals.values())
    return [
        TopicWeight(
            exam=e,
            subject=s,
            topic=t,
            marks_total=w,
            share=w / grand if grand else 0.0,
            weight=w,
            source=UNVERIFIED,
        )
        for (e, s, t), w in totals.items()
    ]


async def store_imports(
    session: AsyncSession, cutoffs: Sequence[CutoffRow], weights: Sequence[TopicWeight]
) -> None:
    """Upsert the cutoffs and weights; the same files imported again change nothing."""
    for c in cutoffs:
        stmt = pg_insert(Cutoff).values(**c.model_dump())
        await session.execute(
            stmt.on_conflict_do_update(
                index_elements=["exam", "year", "tier", "category"],
                set_={"score": stmt.excluded.score, "source_url": stmt.excluded.source_url},
            )
        )
    for w in weights:
        stmt = pg_insert(TopicWeightRow).values(
            exam=w.exam, subject=w.subject, topic=w.topic, weight=w.weight, source=w.source
        )
        await session.execute(
            stmt.on_conflict_do_update(
                index_elements=["exam", "subject", "topic"],
                set_={"weight": stmt.excluded.weight, "source": stmt.excluded.source},
            )
        )
    await session.flush()


async def import_inbox_files(
    session: AsyncSession, inbox: Path, official: frozenset[str]
) -> tuple[int, int]:
    """Import `cutoffs/*.csv` and `weightage/*.csv` from the library inbox.

    Returns (cutoffs stored, weights stored). A cutoff whose `source_url` is not on an
    official domain is dropped; weightage is always labelled `analysis (unverified)`.
    """
    cutoffs = import_cutoffs(read_csv_rows(inbox / "cutoffs"), official)
    weights = aggregate_weightage(import_weightage(read_csv_rows(inbox / "weightage")))
    await store_imports(session, cutoffs, weights)
    return len(cutoffs), len(weights)


def gate_weights(confirmed: Sequence[Any]) -> list[TopicWeight]:
    """Calculate topic weight shares from confirmed PYQs such that shares sum to 1.0."""
    if not confirmed:
        return []

    # Map (subject, topic) -> sum of marks
    totals: dict[tuple[str, str], float] = {}

    for row in confirmed:
        if isinstance(row, dict):
            subject = str(row.get("subject", "General")).strip()
            topic = str(row.get("topic", "")).strip()
            marks_val = row.get("marks", 1.0)
        else:
            subject = str(getattr(row, "subject", "General")).strip()
            topic = str(getattr(row, "topic", "")).strip()
            marks_val = getattr(row, "marks", 1.0)

        if not topic:
            continue

        try:
            marks = float(marks_val)
            if math.isnan(marks) or math.isinf(marks):
                marks = 0.0
            marks = max(0.0, marks)
        except ValueError, TypeError:
            marks = 0.0

        key = (subject, topic)
        totals[key] = totals.get(key, 0.0) + marks

    grand_total = sum(totals.values())
    if grand_total <= 0.0:
        return []

    out: list[TopicWeight] = []
    for (subject, topic), marks_total in totals.items():
        share = marks_total / grand_total
        out.append(
            TopicWeight(
                subject=subject,
                topic=topic,
                marks_total=marks_total,
                share=share,
            )
        )

    return out
