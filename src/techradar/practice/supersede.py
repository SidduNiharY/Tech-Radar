from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import MCQ, FactChange, Flashcard
from techradar.messaging.outbox import enqueue_message
from techradar.pipeline.supersede import load_labels, render_fact_change


async def apply_fact_change(
    session: AsyncSession,
    change_id: int,
    labels: Mapping[str, str],
) -> tuple[int, int]:
    """Retires MCQs and flashcards tied to an outdated fact and enqueues update notice."""
    stmt = select(FactChange).where(FactChange.id == change_id)
    res = await session.execute(stmt)
    change = res.scalar_one_or_none()
    if change is None or change.notified_at is not None:
        return (0, 0)

    # 1. Retire old MCQs
    mcq_stmt = select(MCQ).where(
        MCQ.fact_id == change.old_fact_id,
        MCQ.status != "retired",
    )
    old_mcqs = (await session.execute(mcq_stmt)).scalars().all()
    for m in old_mcqs:
        m.status = "retired"
    mcq_ids = [m.id for m in old_mcqs]
    mcqs_retired = len(old_mcqs)

    # 2. Retire old Flashcards
    card_conditions = [
        and_(Flashcard.source_kind == "fact", Flashcard.source_id == change.old_fact_id),
    ]
    if mcq_ids:
        card_conditions.append(
            and_(Flashcard.source_kind == "mcq", Flashcard.source_id.in_(mcq_ids))
        )

    card_stmt = select(Flashcard).where(
        Flashcard.retired.is_(False),
        or_(*card_conditions),
    )
    old_cards = (await session.execute(card_stmt)).scalars().all()
    for c in old_cards:
        c.retired = True
    cards_retired = len(old_cards)

    # 3. Format and enqueue notification message
    label = labels.get(change.subject_key, change.subject_key)
    msg = render_fact_change(change, label)
    await enqueue_message(session, msg)

    # 4. Mark notified
    change.notified_at = datetime.now(UTC)
    await session.flush()

    return (mcqs_retired, cards_retired)


async def run_fact_changes(
    session: AsyncSession,
    labels: Mapping[str, str] | Path | None = None,
) -> list[tuple[int, int]]:
    """Process all un-notified fact changes."""
    resolved_labels: Mapping[str, str] = {}
    if isinstance(labels, Path):
        resolved_labels = load_labels(labels)
    elif isinstance(labels, Mapping):
        resolved_labels = labels

    stmt = (
        select(FactChange.id).where(FactChange.notified_at.is_(None)).order_by(FactChange.id.asc())
    )
    change_ids = (await session.execute(stmt)).scalars().all()

    results: list[tuple[int, int]] = []
    for cid in change_ids:
        res = await apply_fact_change(session, cid, resolved_labels)
        results.append(res)
    return results


async def fact_changes_job(
    session: AsyncSession,
    labels: Mapping[str, str] | Path | None = None,
) -> list[tuple[int, int]]:
    """Worker task wrapper for periodic fact changes processing."""
    return await run_fact_changes(session, labels)
