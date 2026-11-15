"""Unit tests for regression test suite execution and per-book search tuning."""

from __future__ import annotations

from typing import Any

from techradar.db.models import RegressionCase, Weight
from techradar.feedback.regression import run_regression, save_regression_case
from techradar.feedback.search_tuning import tune_book


class FakeRegressionSession:
    def __init__(self, cases: list[RegressionCase] | None = None) -> None:
        self.cases = cases or []
        self.weights: dict[tuple[str, str], Weight] = {}
        self.logs: list[Any] = []

    def add(self, obj: Any) -> None:
        if isinstance(obj, RegressionCase):
            self.cases.append(obj)
        elif isinstance(obj, Weight):
            self.weights[(obj.kind, obj.key)] = obj
        else:
            self.logs.append(obj)

    async def flush(self) -> None:
        for idx, obj in enumerate(self.cases, 1):
            if getattr(obj, "id", None) is None:
                obj.id = idx

    async def execute(self, stmt: Any) -> Any:
        class Res:
            def __init__(self, items: list[Any]) -> None:
                self.items = items

            def scalars(self) -> Any:
                return self

            def all(self) -> list[Any]:
                return self.items

            def scalar_one_or_none(self) -> Any:
                return self.items[0] if self.items else None

        sql = str(stmt).lower()
        if "from techradar.regression_cases" in sql or "from regression_cases" in sql:
            return Res(self.cases)
        if "from techradar.weights" in sql or "from weights" in sql:
            for (k, _key), w in self.weights.items():
                if k == "search":
                    return Res([w])
            return Res([])
        return Res([])


async def fake_answer_fn(
    text: str,
    status: str = "answered",
    citations: list[str] | None = None,
) -> Any:
    return {
        "text": text,
        "status": status,
        "citations": citations or ["[C1]"],
    }


async def test_case_fails_when_bad_sentence_returns():
    """Regression case fails when the prohibited bad statement reappears in output."""
    case = RegressionCase(
        id=1,
        question="What was the rate decision?",
        doc_id=10,
        bad_answer="RBI cut rates to 1%.",
        must_not_include="RBI cut rates to 1%",
        must_include=None,
        passing=False,
    )
    session = FakeRegressionSession([case])

    async def answer_fn(q: str, doc_id: int | None) -> Any:
        return await fake_answer_fn("RBI cut rates to 1%. More text [C1]")

    rep = await run_regression(session, answer=answer_fn)
    assert rep.failed == 1
    assert rep.passed == 0
    assert rep.failed_ids == [1]


async def test_case_passes_with_must_include():
    """Regression case passes when output includes required factual correction."""
    case = RegressionCase(
        id=2,
        question="What is the current repo rate?",
        doc_id=10,
        bad_answer="The repo rate is 6.5%.",
        must_not_include="The repo rate is 6.5%",
        must_include="The repo rate is 5.25%",
        passing=False,
    )
    session = FakeRegressionSession([case])

    async def answer_fn(q: str, doc_id: int | None) -> Any:
        return await fake_answer_fn("The repo rate is 5.25% as announced today [C1]")

    rep = await run_regression(session, answer=answer_fn)
    assert rep.passed == 1
    assert rep.failed == 0


async def test_save_regression_case():
    """Saving regression case extracts first sentence as must_not_include."""
    session = FakeRegressionSession()
    case_id = await save_regression_case(
        session,
        question="What is inflation?",
        bad_answer="Inflation is negative. It is falling fast.",
        doc_id=5,
    )
    assert case_id == 1
    assert len(session.cases) == 1
    assert session.cases[0].must_not_include == "inflation is negative"


async def test_tuning_only_when_clearly_better():
    """Threshold tuning is rejected if recall gain is under 0.05 threshold."""
    session = FakeRegressionSession()

    async def mock_recall(s: float) -> float:
        return 0.80 if s == 0.30 else 0.83  # only 0.03 gain

    res = await tune_book(session, doc_id=42, recall_at_5=mock_recall)
    assert res is None


async def test_tuning_adopts_when_gain_ge_005():
    """Threshold tuning is adopted when recall gain is >= 0.05."""
    session = FakeRegressionSession()

    async def mock_recall(s: float) -> float:
        return 0.88 if s == 0.35 else 0.80  # 0.08 gain

    res = await tune_book(session, doc_id=42, recall_at_5=mock_recall)
    assert res == 0.35
    assert len(session.logs) == 1
    assert session.logs[0].kind == "search"
