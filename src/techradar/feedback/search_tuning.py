"""Per-book search threshold tuning against evaluation benchmarks."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime

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
