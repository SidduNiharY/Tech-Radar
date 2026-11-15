from __future__ import annotations

import pytest
from sqlalchemy import select

from techradar.db.models import Item, ReviewDecision
from techradar.pipeline.review import ReviewItem, decide, render_review


def test_render_review():
    item = ReviewItem(
        id=42,
        title="Breaking: Tech Announcement",
        domain="techcrunch.com",
        flags=["untrusted_domain", "high_uncertainty"],
    )
    text, buttons = render_review(item)
    assert "Breaking: Tech Announcement" in text
    assert "techcrunch.com" in text
    assert "untrusted_domain" in text
    assert len(buttons) == 1
    assert len(buttons[0]) == 2
    assert buttons[0][0].text == "Keep"
    assert buttons[0][0].data == "keep:42"
    assert buttons[0][1].text == "Discard"
    assert buttons[0][1].data == "drop:42"


@pytest.mark.db
@pytest.mark.asyncio
async def test_keep_sets_new_with_owner_approved(session):
    item = Item(
        raw_item_id=9991,
        title="Review Candidate Keep",
        url="https://example.com/item1",
        domain="example.com",
        lang="en",
        content_hash="hash9991",
        status="needs_review",
        flags=["flag1"],
    )
    session.add(item)
    await session.flush()

    await decide(session, item.id, keep=True)

    stmt = select(Item).where(Item.id == item.id)
    updated = (await session.execute(stmt)).scalar_one()
    assert updated.status == "new"
    assert "owner_approved" in updated.flags

    dec_stmt = select(ReviewDecision).where(ReviewDecision.item_id == item.id)
    decision = (await session.execute(dec_stmt)).scalar_one()
    assert decision.decision == "keep"


@pytest.mark.db
@pytest.mark.asyncio
async def test_discard_filters_out(session):
    item = Item(
        raw_item_id=9992,
        title="Review Candidate Discard",
        url="https://example.com/item2",
        domain="example.com",
        lang="en",
        content_hash="hash9992",
        status="needs_review",
        flags=["spam"],
    )
    session.add(item)
    await session.flush()

    await decide(session, item.id, keep=False)

    stmt = select(Item).where(Item.id == item.id)
    updated = (await session.execute(stmt)).scalar_one()
    assert updated.status == "filtered_out"

    dec_stmt = select(ReviewDecision).where(ReviewDecision.item_id == item.id)
    decision = (await session.execute(dec_stmt)).scalar_one()
    assert decision.decision == "drop"
