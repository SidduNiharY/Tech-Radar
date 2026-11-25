"""Regression cases: bad answers I flagged become tests that guard model changes (Task 8).

SEC: SEC-30, SEC-38.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import Answer, ImprovementLog, RegressionCase

CASE_MIN_AGE_DAYS = 7  # a model change must pass every case at least this old
CASE_SIGNALS = frozenset({"wrong", "down"})
_CITATION = re.compile(r"\[c\d+\]")


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


async def save_case_for_answer(
    session: AsyncSession, answer_id: int, signal: str, *, now: datetime
) -> int | None:
    """A `wrong` or `down` on an answer saves it as a case (once per question and sentence).

    Only an answered, stored answer counts. The save is logged as an automatic change
    (`regression:<id>`), so the weekly report can count the new tests.
    """
    if signal not in CASE_SIGNALS:
        return None
    ans = await session.get(Answer, answer_id)
    if ans is None or ans.status != "answered":
        return None
    must_not = normalize_sentence(ans.text)[:300]
    if not must_not:
        return None
    dup = (
        await session.execute(
            select(RegressionCase.id).where(
                RegressionCase.question == ans.question[:500],
                RegressionCase.must_not_include == must_not,
            )
        )
    ).first()
    if dup is not None:
        return None
    case_id = await save_regression_case(session, question=ans.question, bad_answer=ans.text)
    session.add(
        ImprovementLog(
            kind="content",
            key=f"regression:{case_id}",
            before=None,
            after={"answer_id": answer_id},
            automatic=True,
            at=now,
        )
    )
    await session.flush()
    return case_id


async def set_must_include(
    session: AsyncSession, text: str, answer_id: int | None, *, now: datetime
) -> str:
    """`/fix [<answer id>] <text>`: my own words say what the answer should have said.

    Without an id the latest answer is used. The case is made if it is not saved yet.
    """
    text = " ".join(text.split())[:300]
    if not text:
        return "Usage: /fix <answer id> <what it should say>"
    if answer_id is None:
        answer_id = (
            (
                await session.execute(
                    select(Answer.id).where(Answer.status == "answered").order_by(Answer.id.desc())
                )
            )
            .scalars()
            .first()
        )
    ans = await session.get(Answer, answer_id) if answer_id is not None else None
    if ans is None:
        return "I could not find that answer."
    case = (
        (
            await session.execute(
                select(RegressionCase).where(
                    RegressionCase.question == ans.question[:500],
                    RegressionCase.must_not_include == normalize_sentence(ans.text)[:300],
                )
            )
        )
        .scalars()
        .first()
    )
    if case is None:
        await save_case_for_answer(session, ans.id, "wrong", now=now)
        case = (
            (
                await session.execute(
                    select(RegressionCase).order_by(RegressionCase.id.desc()).limit(1)
                )
            )
            .scalars()
            .first()
        )
    if case is None:
        return "I could not save that."
    case.must_include = text
    await session.flush()
    return "Saved as a test."


def _field(obj: Any, name: str, default: Any = None) -> Any:
    return getattr(obj, name, None) or (
        obj.get(name, default) if isinstance(obj, dict) else default
    )


async def run_regression(
    session: AsyncSession,
    answer: Callable[[str, int | None], Awaitable[Any]],
    *,
    older_than_days: int = 0,
    now: datetime | None = None,
) -> RegressionReport:
    """Run the saved cases. A case passes when the answer is `answered`, has citations, does
    not contain `must_not_include`, and contains `must_include` when that is set.
    """
    ts = now or datetime.now(UTC)
    stmt = select(RegressionCase)
    if older_than_days > 0:
        stmt = stmt.where(RegressionCase.created_at <= ts - timedelta(days=older_than_days))
    cases = (await session.execute(stmt)).scalars().all()

    passed = 0
    failed_ids: list[int] = []
    for c in cases:
        ans = await answer(c.question, c.doc_id)
        text = " ".join(str(_field(ans, "text", "") or "").lower().split())
        status = _field(ans, "status", "answered")
        cited = bool(_field(ans, "citations")) or bool(_CITATION.search(text))
        bad = " ".join(c.must_not_include.lower().split())
        ok = (
            status == "answered"
            and cited
            and (not bad or bad not in text)
            and (not c.must_include or " ".join(c.must_include.lower().split()) in text)
        )
        c.passing = ok
        c.last_run_at = ts
        if ok:
            passed += 1
        else:
            failed_ids.append(c.id)
    await session.flush()
    return RegressionReport(passed=passed, failed=len(failed_ids), failed_ids=failed_ids)


# --- the model-change hook (Task 8) ---------------------------------------------------------


def regression_metrics(report: RegressionReport) -> dict[str, Any]:
    """What a candidate model's bench run stores next to its other metrics."""
    return {"regression_failed": report.failed, "regression_failed_ids": report.failed_ids[:50]}


def regression_refusal(metrics: Mapping[str, Any]) -> str | None:
    """None when the candidate may become a `worker`, `checker` or `night` model.

    A candidate whose bench run did not measure the cases, or failed any case older than 7 days,
    is refused with `fails <n> regression cases` (a missing measurement counts as a failure).
    """
    failed = metrics.get("regression_failed")
    if failed is None:
        return "fails an unmeasured number of regression cases"
    return f"fails {int(failed)} regression cases" if int(failed) > 0 else None
