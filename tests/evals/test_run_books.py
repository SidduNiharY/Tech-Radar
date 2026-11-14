"""`make rag-eval` includes the book evals (Phase 2c Task 11) and never hides mock mode."""

from __future__ import annotations

from typing import Any

from evals.rag import run
from evals.rag.book_evals import BookEvalCase


class _Session:
    async def __aenter__(self) -> _Session:
        return self

    async def __aexit__(self, *_a: Any) -> None:
        return None


def _factory() -> _Session:
    return _Session()


def _cases(*expected: int) -> list[BookEvalCase]:
    return [
        BookEvalCase(id=i, doc_id=7, question=f"q{i}", expected_chunk_ids=[e])
        for i, e in enumerate(expected, start=1)
    ]


async def test_book_report_scores_each_book_question_scoped_to_its_book():
    seen: list[tuple[str, Any]] = []

    async def cases(_session: Any) -> list[BookEvalCase]:
        return _cases(1, 2, 3, 4, 5)

    async def fake_retrieve(question: str, _deps: Any, *, doc_id: int) -> list[Any]:
        seen.append((question, doc_id))
        hit = type("H", (), {"chunk_id": int(question[1:]) if question != "q5" else 99})
        return [hit]

    report = await run.book_eval_report(
        _factory, object(), cases_fn=cases, retrieve_fn=fake_retrieve
    )
    assert report["cases"] == 5
    assert report["recall@5"] == 0.8
    assert report["passed"] is True
    assert all(doc_id == 7 for _, doc_id in seen)


async def test_book_report_fails_below_threshold():
    async def cases(_session: Any) -> list[BookEvalCase]:
        return _cases(1, 2)

    async def fake_retrieve(question: str, _deps: Any, *, doc_id: int) -> list[Any]:
        return []

    report = await run.book_eval_report(
        _factory, object(), cases_fn=cases, retrieve_fn=fake_retrieve
    )
    assert report["recall@5"] == 0.0
    assert report["passed"] is False


async def test_mock_mode_says_waiting_and_skips_book_evals(tmp_path, capsys):
    report, _ = await run.evaluate_rag(results_dir=tmp_path, use_mock=True)
    out = capsys.readouterr().out
    assert "WAITING: internet stage" in out
    assert report["mode"] == "mock"
    assert report["book_evals"]["status"] == "waiting"
