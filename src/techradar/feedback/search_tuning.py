"""Per-book search threshold tuning against evaluation benchmarks."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import ImprovementLog, Weight


async def tune_book(
    session: AsyncSession,
    doc_id: int,
    recall_at_5: Callable[[float], Awaitable[float]],
    grid: Sequence[float] = (0.20, 0.25, 0.30, 0.35, 0.40, 0.45),
    now: datetime | None = None,
) -> float | None:
    """Tune min_score for document retrieval, adopting only if beating current recall by >=0.05."""
    ts = now or datetime.now(UTC)
    weight_key = f"doc:{doc_id}"

    # Load current threshold or default 0.30
    stmt = select(Weight).where(Weight.kind == "search", Weight.key == weight_key)
    res = await session.execute(stmt)
    w_row = res.scalar_one_or_none()
    current_thresh = w_row.value if w_row else 0.30

    current_recall = await recall_at_5(current_thresh)

    best_thresh = current_thresh
    best_recall = current_recall

    for thresh in grid:
        rec = await recall_at_5(thresh)
        if rec > best_recall:
            best_recall = rec
            best_thresh = thresh

    # Adopt only if improvement is at least 0.05
    if (best_recall - current_recall) < 0.05 or best_thresh == current_thresh:
        return None

    # Values must stay within 0.20 to 0.45
    clamped_thresh = max(0.20, min(0.45, round(best_thresh, 4)))

    if w_row:
        old_val = w_row.value
        w_row.value = clamped_thresh
        w_row.updated_at = ts
    else:
        old_val = current_thresh
        w_row = Weight(
            kind="search",
            key=weight_key,
            value=clamped_thresh,
            updated_at=ts,
        )
        session.add(w_row)

    log = ImprovementLog(
        kind="search",
        key=weight_key,
        before={"value": old_val, "recall": current_recall},
        after={"value": clamped_thresh, "recall": best_recall},
        automatic=True,
        at=ts,
    )
    session.add(log)
    await session.flush()
    return clamped_thresh


# --- Phase 11 Task 8: reading the tuned value, and the weekly job ---------------------------

MIN_EVALS = 5  # a book needs this many retrieval checks before it is tuned
TUNE_LO, TUNE_HI = 0.20, 0.45


async def book_min_score(session: AsyncSession, doc_id: int) -> float | None:
    """The tuned cut-off of one book, kept inside 0.20 to 0.45, or None when none is stored."""
    row = (
        await session.execute(
            select(Weight).where(Weight.kind == "search", Weight.key == f"doc:{doc_id}")
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    return max(TUNE_LO, min(TUNE_HI, float(row.value)))


async def run_tune_books(
    session: AsyncSession, retrieve_hits: Any, *, now: datetime
) -> dict[int, float | None]:
    """The weekly job body: tune every ready book that has enough retrieval checks.

    `retrieve_hits(question, doc_id)` returns the top hits as (chunk id, score) pairs; it is
    called once per check and the same hits are scored against every cut-off in the grid.
    Recall@5 is the share of checks whose expected chunk is among the top 5 hits that score at
    least the cut-off. A value is stored only if it beats the current one by 0.05 (tune_book).
    """
    from techradar.db.models import BookEval, LibraryDoc

    results: dict[int, float | None] = {}
    docs = (
        (await session.execute(select(LibraryDoc.id).where(LibraryDoc.status == "ready")))
        .scalars()
        .all()
    )
    for doc_id in docs:
        evals = (
            (await session.execute(select(BookEval).where(BookEval.doc_id == doc_id)))
            .scalars()
            .all()
        )
        if len(evals) < MIN_EVALS:
            continue
        cached: list[tuple[set[int], list[tuple[int, float]]]] = []
        for ev in evals:
            hits = list(await retrieve_hits(ev.question, doc_id))[:5]
            cached.append((set(ev.expected_chunk_ids), hits))

        async def recall(threshold: float, _cached: Any = cached) -> float:
            found = sum(
                1 for want, hits in _cached if any(c in want and s >= threshold for c, s in hits)
            )
            return found / len(_cached)

        results[doc_id] = await tune_book(session, doc_id, recall, now=now)
    return results
