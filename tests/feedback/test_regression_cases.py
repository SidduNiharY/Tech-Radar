"""Regression cases from flagged answers, the model-change hook and tuning (Phase 11 Task 8)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select

from techradar.bot.routing import route_update
from techradar.db.models import Answer, ImprovementLog, RegressionCase, Weight
from techradar.feedback.regression import (
    RegressionReport,
    regression_metrics,
    regression_refusal,
    run_regression,
    save_case_for_answer,
    set_must_include,
)
from techradar.feedback.search_tuning import book_min_score, tune_book
from techradar.rag.answer import answer_question
from tests.fakes import FakeCompleter
from tests.rag.test_answer import HITS, make_deps

NOW = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)


def test_fix_is_the_owners_alone() -> None:
    assert route_update(42, "/fix 5 the repo rate is 5.25%", 42).action == "fix"
    assert route_update(-100, "/fix 5 x", 42, group_ids=frozenset({-100})).action == "ignore"


def test_model_change_is_refused_on_regression_failure() -> None:
    report = RegressionReport(passed=2, failed=1, failed_ids=[7])
    assert regression_refusal(regression_metrics(report)) == "fails 1 regression cases"
    assert regression_refusal(regression_metrics(RegressionReport(passed=3, failed=0))) is None
    # a candidate whose bench run did not measure the cases is not allowed through
    assert regression_refusal({}) is not None


async def test_per_book_min_score_replaces_the_default(monkeypatch: pytest.MonkeyPatch) -> None:
    low = HITS[0].model_copy(update={"score": 0.25})

    async def mock_retrieve(*args: Any, **kwargs: Any) -> Any:
        return [low]

    monkeypatch.setattr("techradar.rag.answer.retrieve", mock_retrieve)
    cited = '{"answer": "The repo rate is 6.5% [C1].", "citations": ["C1"]}'
    deps = make_deps([low], FakeCompleter([cited]), min_score=0.30)
    plain = await answer_question("repo rate?", deps)
    assert plain.status == "not_found"  # 0.25 is under the default 0.30
    deps = make_deps([low], FakeCompleter([cited]), min_score=0.30)
    tuned = await answer_question("repo rate?", deps, min_score=0.20)
    assert tuned.status == "answered"


@pytest.mark.db
async def test_wrong_on_an_answer_saves_one_case_and_logs_it(session) -> None:
    ans = Answer(
        chat_id=42,
        question="What is the rate?",
        text="RBI cut rates to 1%. More [C1]",
        status="answered",
    )
    session.add(ans)
    await session.flush()
    assert await save_case_for_answer(session, ans.id, "up", now=NOW) is None
    case_id = await save_case_for_answer(session, ans.id, "wrong", now=NOW)
    assert case_id is not None
    assert await save_case_for_answer(session, ans.id, "down", now=NOW) is None  # once
    case = await session.get(RegressionCase, case_id)
    assert case is not None and case.must_not_include == "rbi cut rates to 1%"
    log = (
        await session.execute(
            select(ImprovementLog).where(ImprovementLog.key == f"regression:{case_id}")
        )
    ).scalar_one()
    assert log.automatic is True


@pytest.mark.db
async def test_fix_sets_must_include_on_the_case(session) -> None:
    ans = Answer(chat_id=42, question="Rate?", text="It is 6.5%. [C1]", status="answered")
    session.add(ans)
    await session.flush()
    assert (
        await set_must_include(session, "The rate is 5.25%", ans.id, now=NOW) == "Saved as a test."
    )
    case = (await session.execute(select(RegressionCase))).scalar_one()
    assert case.must_include == "The rate is 5.25%"
    assert (await set_must_include(session, "   ", ans.id, now=NOW)).startswith("Usage")


@pytest.mark.db
async def test_only_cases_older_than_the_limit_guard_a_model_change(session) -> None:
    old = RegressionCase(
        question="q1",
        bad_answer="bad one.",
        must_not_include="bad one",
        passing=False,
        created_at=NOW - timedelta(days=10),
    )
    new = RegressionCase(
        question="q2",
        bad_answer="bad two.",
        must_not_include="bad two",
        passing=False,
        created_at=NOW - timedelta(days=1),
    )
    session.add_all([old, new])
    await session.flush()

    async def bad_again(q: str, doc_id: int | None) -> Any:
        return {"text": "bad one. bad two. [C1]", "status": "answered", "citations": ["C1"]}

    rep = await run_regression(session, bad_again, older_than_days=7, now=NOW)
    assert rep.failed == 1 and rep.failed_ids == [old.id]
    assert regression_refusal(regression_metrics(rep)) == "fails 1 regression cases"


@pytest.mark.db
async def test_tuning_stores_a_clamped_value_and_logs_it(session) -> None:
    async def recall(s: float) -> float:
        return 0.9 if s == 0.40 else 0.7

    assert await tune_book(session, 4242, recall, now=NOW) == 0.40
    assert await book_min_score(session, 4242) == 0.40
    w = (await session.execute(select(Weight).where(Weight.key == "doc:4242"))).scalar_one()
    w.value = 0.9  # a bad stored value is still read inside 0.20 to 0.45
    await session.flush()
    assert await book_min_score(session, 4242) == 0.45
    assert await book_min_score(session, 999999) is None


@pytest.mark.db
async def test_tuning_only_when_clearly_better(session) -> None:
    async def recall(s: float) -> float:
        return 0.80 if s == 0.30 else 0.83

    assert await tune_book(session, 4243, recall, now=NOW) is None
