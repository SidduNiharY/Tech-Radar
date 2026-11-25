# The scheduler is pure Python behind the CardScheduler Protocol: `fsrs` (py-fsrs) is not an
# approved dependency, so a server that approves it can inject its scheduler with set_scheduler.
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field
from sqlalchemy import DateTime, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import Chunk, Flashcard
from techradar.feedback.signals import TargetKind, feedback_buttons
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
    # What today already used: new cards first shown today, and cards reviewed today (their
    # FSRS state keeps `last_review`); the rest of today's budget is what is left.
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    new_today = await session.scalar(
        select(func.count())
        .select_from(Flashcard)
        .where(Flashcard.first_shown_at >= day_start, Flashcard.first_shown_at <= now)
    )
    reviewed_today = await session.scalar(
        select(func.count())
        .select_from(Flashcard)
        .where(
            Flashcard.first_shown_at < day_start,
            cast(Flashcard.fsrs_card["last_review"].astext, DateTime(timezone=True)) >= day_start,
        )
    )
    new_limit = max(0, new_limit - int(new_today or 0))
    review_limit = max(0, review_limit - int(reviewed_today or 0))

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
    buttons += feedback_buttons(TargetKind.CARD, c.id)  # --- Phase 11 ---

    return text, buttons


async def rate_card(
    session: AsyncSession,
    card_id: int,
    rating: Literal[1, 2, 3, 4],
    now: datetime,
) -> Literal["rated", "already_rated", "not_found"]:
    """Apply a rating once. A second tap on an old button finds the card no longer due."""
    card = await session.get(Flashcard, card_id)
    if card is None or card.retired:
        return "not_found"
    if card.due > now and card.first_shown_at is not None and card.fsrs_card.get("last_review"):
        return "already_rated"
    state, due = review_card(dict(card.fsrs_card or {}), rating, now)
    card.fsrs_card = state
    card.due = due
    if card.first_shown_at is None:
        card.first_shown_at = now
    await session.flush()
    return "rated"


async def reveal_card(session: AsyncSession, card_id: int) -> tuple[str, list[list[Button]]] | None:
    """The back of a card with its source line and the rating buttons; None if gone."""
    card = await session.get(Flashcard, card_id)
    if card is None or card.retired:
        return None
    title: str | None = None
    if card.chunk_id is not None:
        title = await session.scalar(select(Chunk.title).where(Chunk.id == card.chunk_id))
    row = CardRow(
        id=card.id,
        front=card.front,
        back=card.back,
        source_kind=card.source_kind,
        due=card.due,
        doc_path=card.doc_path,
        page=card.page,
        ts_start=card.ts_start,
    )
    return render_card_back(row, title)


SOURCE_CHARS = 1500


async def source_text(session: AsyncSession, card_id: int) -> str | None:
    """`From <title>, p. <n>:` and the cited chunk's text (cut to 1,500 characters)."""
    card = await session.get(Flashcard, card_id)
    if card is None or card.chunk_id is None:
        return None
    chunk = await session.get(Chunk, card.chunk_id)
    if chunk is None:
        return None
    where = f", p. {chunk.page}" if chunk.page is not None else ""
    return f"From {chunk.title}{where}:\n{chunk.text[:SOURCE_CHARS]}"


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
