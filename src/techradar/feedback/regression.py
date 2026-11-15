"""Regression cases runner to guard against regressions on answered queries."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import RegressionCase


class RegressionReport(BaseModel):
    """Result of running regression benchmark against saved failure cases."""

    passed: int = Field(ge=0)
    failed: int = Field(ge=0)
    failed_ids: list[int] = Field(default_factory=list)


def normalize_sentence(text: str) -> str:
    """Extract and normalize first sentence for must_not_include matching."""
    first = text.strip().split(".")[0].strip()
    return " ".join(first.lower().split())


async def save_regression_case(
    session: AsyncSession,
    *,
    question: str,
    bad_answer: str,
    doc_id: int | None = None,
    from_feedback_id: int | None = None,
    must_include: str | None = None,
) -> int:
    """Save an answer with negative feedback as a permanent regression test case."""
    must_not = normalize_sentence(bad_answer)[:300]
    case = RegressionCase(
        question=question[:500],
        doc_id=doc_id,
        bad_answer=bad_answer,
        must_not_include=must_not,
        must_include=must_include[:300] if must_include else None,
        from_feedback_id=from_feedback_id,
        passing=False,
    )
    session.add(case)
    await session.flush()
    return case.id


async def run_regression(
    session: AsyncSession,
    answer: Callable[[str, int | None], Awaitable[Any]],
    *,
    older_than_days: int = 0,
    now: datetime | None = None,
) -> RegressionReport:
    """Execute regression suite and verify answers avoid known bad statements."""
    ts = now or datetime.now(UTC)
    stmt = select(RegressionCase)
    if older_than_days > 0:
        cutoff = ts - timedelta(days=older_than_days)
        stmt = stmt.where(
            (RegressionCase.last_run_at.is_(None)) | (RegressionCase.last_run_at <= cutoff)
        )

    res = await session.execute(stmt)
    cases = res.scalars().all()

    passed = 0
    failed = 0
    failed_ids: list[int] = []

    for c in cases:
        ans_obj = await answer(c.question, c.doc_id)
        # Verify status is answered
        status = getattr(ans_obj, "status", None) or (
            ans_obj.get("status") if isinstance(ans_obj, dict) else "answered"
        )
        ans_text = getattr(ans_obj, "text", "") or (
            ans_obj.get("text", "") if isinstance(ans_obj, dict) else str(ans_obj)
        )
        citations = getattr(ans_obj, "citations", None) or (
            ans_obj.get("citations") if isinstance(ans_obj, dict) else None
        )

        norm_ans = " ".join(ans_text.lower().split())
        norm_must_not = " ".join(c.must_not_include.lower().split())

        has_citations = bool(citations) or bool(
            "[c" in norm_ans or "[1]" in norm_ans or "[c1]" in norm_ans
        )
        status_ok = status == "answered"
        not_contains_bad = norm_must_not not in norm_ans if norm_must_not else True
        contains_good = (
            (" ".join(c.must_include.lower().split()) in norm_ans) if c.must_include else True
        )

        case_passed = bool(status_ok and has_citations and not_contains_bad and contains_good)

        c.passing = case_passed
        c.last_run_at = ts

        if case_passed:
            passed += 1
        else:
            failed += 1
            failed_ids.append(c.id)

    await session.flush()
    return RegressionReport(
        passed=passed,
        failed=failed,
        failed_ids=failed_ids,
    )
