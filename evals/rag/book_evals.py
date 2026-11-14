"""Book evals for `make rag-eval` (Phase 2c Task 7).

Each library book has questions in `book_evals`, one per chunk that answers it. This checks
that retrieval, scoped to the book, finds that chunk in its top 5.

SEC: SEC-41.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from evals.rag.metrics import recall_at_k
from techradar.db.models import BookEval
from techradar.rag.retrieve import RagDeps, RetrieveFilters, retrieve

# (question, doc_id) -> chunk ids, best first
Retriever = Callable[[str, int], Awaitable[list[int]]]

THRESHOLD_BOOK_RECALL_AT_5 = 0.80


@dataclass(frozen=True)
class BookEvalCase:
    """One stored book question and the chunk(s) that answer it."""

    id: int
    doc_id: int
    question: str
    expected_chunk_ids: list[int]


async def book_eval_cases(session: AsyncSession) -> list[BookEvalCase]:
    """Every stored book eval, oldest first."""
    rows = await session.execute(select(BookEval).order_by(BookEval.id))
    return [
        BookEvalCase(
            id=r.id,
            doc_id=r.doc_id,
            question=r.question,
            expected_chunk_ids=list(r.expected_chunk_ids),
        )
        for r in rows.scalars()
    ]


def make_retriever(deps: RagDeps, retrieve_fn: Callable[..., Any] = retrieve) -> Retriever:
    """A Retriever over `retrieve`, scoped to the book when retrieve can be.

    `retrieve` gets a `doc_id` scope in a later task. Until then (or if the scope lives on
    `RetrieveFilters`) this adapts to what exists, so the eval keeps running unscoped.
    """

    async def run(question: str, doc_id: int) -> list[int]:
        kwargs: dict[str, Any] = {}
        if "doc_id" in inspect.signature(retrieve_fn).parameters:
            kwargs["doc_id"] = doc_id
        elif "doc_id" in RetrieveFilters.model_fields:
            kwargs["f"] = RetrieveFilters(doc_id=doc_id)
        hits = await retrieve_fn(question, deps, **kwargs)
        return [h.chunk_id for h in hits]

    return run


async def recall_at_5(cases: list[BookEvalCase], retriever: Retriever) -> float:
    """Mean recall@5 over the cases (1.0 when there are none)."""
    if not cases:
        return 1.0
    scores: list[float] = []
    for case in cases:
        ranked = await retriever(case.question, case.doc_id)
        scores.append(
            recall_at_k([str(i) for i in ranked], [str(i) for i in case.expected_chunk_ids], k=5)
        )
    return sum(scores) / len(scores)
