"""The review inbox: items the pipeline held back for the owner (Phase 3 Task 8).

An item's title and domain come from a web page, so they are cleaned and cut before they are
shown; Keep and Discard are the owner's alone (the bot checks the chat before calling `decide`).

SEC: SEC-20, SEC-24, SEC-26.
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import Item, ReviewDecision
from techradar.messaging.outbox import Button
from techradar.security.text import sanitize_text

TITLE_CHARS = 200


class ReviewItem(BaseModel):
    id: int
    title: str
    domain: str
    flags: list[str] = Field(default_factory=list)


async def next_review_item(session: AsyncSession) -> ReviewItem | None:
    """The oldest item waiting for the owner's decision."""
    item = (
        await session.execute(
            select(Item).where(Item.status == "needs_review").order_by(Item.id.asc()).limit(1)
        )
    ).scalar_one_or_none()
    if item is None:
        return None
    return ReviewItem(
        id=item.id, title=item.title, domain=item.domain, flags=list(item.flags or [])
    )


def render_review(i: ReviewItem) -> tuple[str, list[list[Button]]]:
    """Plain text (no markup) with Keep (`keep:<id>`) and Discard (`drop:<id>`)."""
    title = sanitize_text(i.title)[:TITLE_CHARS]
    flags_text = ", ".join(i.flags) if i.flags else "none"
    text = f"Review needed:\nTitle: {title}\nDomain: {sanitize_text(i.domain)}\nFlags: {flags_text}"
    buttons = [
        [
            Button(text="Keep", data=f"keep:{i.id}"),
            Button(text="Discard", data=f"drop:{i.id}"),
        ]
    ]
    return text, buttons


async def decide(session: AsyncSession, item_id: int, keep: bool) -> bool:
    """Keep (status `new` plus flag `owner_approved`) or discard (`filtered_out`) one item.

    Returns False, and records nothing, when the item is gone or no longer waiting: a second
    tap on an old button changes nothing. Either decision is recorded in `review_decisions`.
    """
    item = (await session.execute(select(Item).where(Item.id == item_id))).scalar_one_or_none()
    if item is None or item.status != "needs_review":
        return False
    if keep:
        item.status = "new"
        flags = list(item.flags or [])
        if "owner_approved" not in flags:
            flags.append("owner_approved")
        item.flags = flags
    else:
        item.status = "filtered_out"
    session.add(ReviewDecision(item_id=item_id, decision="keep" if keep else "drop"))
    await session.flush()
    return True
