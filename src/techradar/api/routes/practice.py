"""Flashcards on the web: due fronts, a card's back, and a rating (Phase 3 cards).

GET routes read through `tr_ro`, so listing due cards does not mark them shown; a card
counts as shown when it is first rated. Only a due card can be rated, so a repeated or
replayed rating cannot push a card further out (409).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from techradar.api.deps import AppSession, DbId, Now, RoSession
from techradar.api.schemas import CardBackResponse, CardOut, RateCardRequest, RateCardResponse
from techradar.db.models import Flashcard
from techradar.practice.flashcards import due_cards, review_card

router = APIRouter(prefix="/practice/cards", tags=["practice"])

NEW_LIMIT = 10  # D39 daily limits
REVIEW_LIMIT = 40


@router.get("/due", response_model=list[CardOut])
async def cards_due(session: RoSession, now: Now) -> list[CardOut]:
    rows = await due_cards(session, now, new_limit=NEW_LIMIT, review_limit=REVIEW_LIMIT)
    return [CardOut(id=c.id, front=c.front) for c in rows]


@router.get("/{card_id}/back", response_model=CardBackResponse)
async def card_back(card_id: DbId, session: RoSession) -> CardBackResponse:
    card = await session.get(Flashcard, card_id)
    if card is None or card.retired:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    return CardBackResponse(back=card.back)


@router.post("/{card_id}/rate", response_model=RateCardResponse)
async def rate_card(
    card_id: DbId, body: RateCardRequest, session: AppSession, now: Now
) -> RateCardResponse:
    card = (
        await session.execute(select(Flashcard).where(Flashcard.id == card_id).with_for_update())
    ).scalar_one_or_none()
    if card is None or card.retired:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    if card.due > now:
        raise HTTPException(status.HTTP_409_CONFLICT, "This card is not due yet")
    state, next_due = review_card(dict(card.fsrs_card or {}), body.rating, now)  # type: ignore[arg-type]
    card.fsrs_card = state
    card.due = next_due
    if card.first_shown_at is None:
        card.first_shown_at = now
    await session.commit()
    return RateCardResponse(next_due=next_due)
