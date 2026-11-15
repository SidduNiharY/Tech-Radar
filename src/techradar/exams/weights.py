from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from typing import Any
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field


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
