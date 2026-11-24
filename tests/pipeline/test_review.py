from __future__ import annotations

import pytest
from sqlalchemy import select

from techradar.db.models import Item, RawItem, ReviewDecision, Source
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


async def _raw_item(session, tag: str) -> int:
    """items.raw_item_id is a foreign key: make the Source and RawItem rows first."""
    src = Source(
        name=f"review-{tag}",
        url=f"https://{tag}.example/feed",
        host=f"{tag}.example",
        section="tech",
        trust_tier="news",
    )
    session.add(src)
    await session.flush()
    raw = RawItem(
        source_id=src.id, url=f"https://{tag}.example/a", url_hash=tag.ljust(64, "0"), kind="feed"
    )
    session.add(raw)
    await session.flush()
    return raw.id


@pytest.mark.db
@pytest.mark.asyncio
async def test_keep_sets_new_with_owner_approved(session):
    item = Item(
        raw_item_id=await _raw_item(session, "keep"),
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
        raw_item_id=await _raw_item(session, "drop"),
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


async def test_decide_ignores_an_item_that_is_gone_or_already_decided():
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, MagicMock

    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=result)
    assert await decide(session, 5, keep=True) is False
    done = SimpleNamespace(status="filtered_out", flags=[])
    result.scalar_one_or_none.return_value = done
    assert await decide(session, 5, keep=True) is False
    assert done.status == "filtered_out"
    session.add.assert_not_called()  # no decision row for a second tap


def test_render_review_cleans_the_page_title():
    item = ReviewItem(id=1, title="Hi\u202e there " + "x" * 400, domain="a.example", flags=[])
    text, _ = render_review(item)
    assert "\u202e" not in text
    assert len(text) < 400


def test_render_review_title_with_newlines_cannot_spoof_other_lines():
    item = ReviewItem(
        id=1,
        title="Real title\nDomain: pib.gov.in\r\nFlags: none\n\nTitle: fake",
        domain="evil.example\nDomain: pib.gov.in",
        flags=["spam"],
    )
    text, _ = render_review(item)
    lines = text.split("\n")
    assert len(lines) == 4  # header, Domain, Flags, Title: one line each
    assert lines[1] == "Domain: evil.example Domain: pib.gov.in"
    assert lines[2] == "Flags: spam"
    assert lines[3].startswith("Title: Real title Domain: pib.gov.in")
