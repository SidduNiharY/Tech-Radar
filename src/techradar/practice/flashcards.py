# WIRING(claude): routing quiz, cards; callbacks ans, rate
# WIRING(claude): jobs quiz_job, cards_job, mistakes_page_job
# WIRING(claude): needs fsrs (not approved) behind CardScheduler Protocol
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import Flashcard
from techradar.messaging.outbox import Button, enqueue_message
from techradar.practice.fsrs import Card, Rating, schedule_card


class CardRow(BaseModel):
    id: int
    front: str
    back: str
    source_kind: str
    due: datetime
    is_new: bool = False
    doc_path: str | None = None
    page: int | None = None
    ts_start: int | None = None


class CardScheduler(Protocol):
    """Protocol abstracting spaced repetition card scheduling (e.g. FSRS)."""

    def new_card(self, now: datetime) -> tuple[dict[str, Any], datetime]: ...

    def review_card(
        self,
        state: dict[str, Any],
        rating: Literal[1, 2, 3, 4],
        now: datetime,
    ) -> tuple[dict[str, Any], datetime]: ...


class DefaultFSRSScheduler:
    """Pure Python deterministic FSRS scheduler implementing CardScheduler."""

    def new_card(self, now: datetime) -> tuple[dict[str, Any], datetime]:
        card = Card(due=now)
        return card.to_dict(), now

    def review_card(
        self,
        state: dict[str, Any],
        rating: Literal[1, 2, 3, 4],
        now: datetime,
    ) -> tuple[dict[str, Any], datetime]:
        card = Card.from_dict(state) if state else Card(due=now)
        updated = schedule_card(card, Rating(rating), now)
        return updated.to_dict(), updated.due


_scheduler: CardScheduler = DefaultFSRSScheduler()


def get_scheduler() -> CardScheduler:
    return _scheduler


def set_scheduler(scheduler: CardScheduler) -> None:
    global _scheduler
    _scheduler = scheduler


def new_card_state(now: datetime) -> tuple[dict[str, Any], datetime]:
    """Generates initial state dictionary and due date for a new card."""
    return _scheduler.new_card(now)


def review_card(
    state: dict[str, Any],
    rating: Literal[1, 2, 3, 4],
    now: datetime,
) -> tuple[dict[str, Any], datetime]:
    """Computes updated state dictionary and next due date based on review rating."""
    return _scheduler.review_card(state, rating, now)


async def due_cards(
    session: AsyncSession,
    now: datetime,
    *,
    new_limit: int = 10,
    review_limit: int = 40,
) -> list[CardRow]:
    """Fetches due cards up to daily limits:

    - up to review_limit review cards (first_shown_at is not None, oldest due first)
    - up to new_limit new cards (first_shown_at is None, not yet shown)
    - retired cards never
    """
    # 1. Review cards (shown previously)
    review_stmt = (
        select(Flashcard)
        .where(
            Flashcard.retired.is_(False),
            Flashcard.first_shown_at.is_not(None),
            Flashcard.due <= now,
        )
        .order_by(Flashcard.due.asc())
        .limit(review_limit)
    )
    review_res = await session.execute(review_stmt)
    review_cards = list(review_res.scalars().all())

    # 2. New cards (never shown before)
    new_stmt = (
        select(Flashcard)
        .where(
            Flashcard.retired.is_(False),
            Flashcard.first_shown_at.is_(None),
            Flashcard.due <= now,
        )
        .order_by(Flashcard.due.asc(), Flashcard.id.asc())
        .limit(new_limit)
    )
    new_res = await session.execute(new_stmt)
    new_cards = list(new_res.scalars().all())

    rows: list[CardRow] = []
    for c in review_cards:
        rows.append(
            CardRow(
                id=c.id,
                front=c.front,
                back=c.back,
                source_kind=c.source_kind,
                due=c.due,
                is_new=False,
                doc_path=c.doc_path,
                page=c.page,
                ts_start=c.ts_start,
            )
        )
    for c in new_cards:
        rows.append(
            CardRow(
                id=c.id,
                front=c.front,
                back=c.back,
                source_kind=c.source_kind,
                due=c.due,
                is_new=True,
                doc_path=c.doc_path,
                page=c.page,
                ts_start=c.ts_start,
            )
        )
    return rows


def render_card_back(
    c: CardRow,
    doc_title: str | None = None,
) -> tuple[str, list[list[Button]]]:
    """Renders the back of a flashcard with source attribution and rating buttons.

    Adds 'Source: <doc title>, p. <n>' (or <mm:ss>) and 'Show source' button (src:<card_id>).
    Rating buttons: Again, Hard, Good, Easy with rate:<card_id>:<1-4>.
    """
    title = doc_title or (Path(c.doc_path).stem if c.doc_path else None)
    source_parts: list[str] = []

    if title:
        source_parts.append(title)

    if c.page is not None:
        source_parts.append(f"p. {c.page}")
    elif c.ts_start is not None:
        mins = c.ts_start // 60
        secs = c.ts_start % 60
        source_parts.append(f"{mins:02d}:{secs:02d}")

    text = c.back
    has_source = bool(source_parts) or (c.doc_path is not None)
    if source_parts:
        text = f"{text}\n\nSource: {', '.join(source_parts)}"

    buttons: list[list[Button]] = [
        [
            Button(text="Again", data=f"rate:{c.id}:1"),
            Button(text="Hard", data=f"rate:{c.id}:2"),
            Button(text="Good", data=f"rate:{c.id}:3"),
            Button(text="Easy", data=f"rate:{c.id}:4"),
        ]
    ]

    if has_source:
        buttons.append([Button(text="Show source", data=f"src:{c.id}")])

    return text, buttons


class CardsResult(BaseModel):
    cards_sent: int = 0
    card_ids: list[int] = Field(default_factory=list)
    skipped_reason: str | None = None


async def run_cards(
    session: AsyncSession,
    *,
    now: datetime,
    owner_chat_id: int,
    new_limit: int = 10,
    review_limit: int = 40,
) -> CardsResult:
    """Job body for cards_job. Enqueues due cards to owner_chat_id."""
    cards = await due_cards(session, now, new_limit=new_limit, review_limit=review_limit)
    if not cards:
        return CardsResult(skipped_reason="no_due_cards")

    card_ids: list[int] = []
    for c in cards:
        text = f"📇 Flashcard\n\n{c.front}"
        buttons = [[Button(text="Show Answer", data=f"card_show:{c.id}")]]
        await enqueue_message(
            session,
            chat_id=owner_chat_id,
            text=text,
            buttons=buttons,
            purpose="cards",
            ref_id=c.id,
        )
        if c.is_new:
            fc = await session.get(Flashcard, c.id)
            if fc is not None and fc.first_shown_at is None:
                fc.first_shown_at = now
        card_ids.append(c.id)

    await session.flush()
    return CardsResult(cards_sent=len(cards), card_ids=card_ids)
