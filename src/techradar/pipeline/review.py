from __future__ import annotations

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import Item, ReviewDecision
from techradar.messaging.outbox import Button


class ReviewItem(BaseModel):
    id: int
    title: str
    domain: str
    flags: list[str] = Field(default_factory=list)


async def next_review_item(session: AsyncSession) -> ReviewItem | None:
    """Fetch the oldest item needing review."""
    stmt = select(Item).where(Item.status == "needs_review").order_by(Item.id.asc()).limit(1)
    res = await session.execute(stmt)
    item = res.scalar_one_or_none()
    if item is None:
        return None
    return ReviewItem(
        id=item.id,
        title=item.title,
        domain=item.domain,
        flags=list(item.flags or []),
    )


def render_review(i: ReviewItem) -> tuple[str, list[list[Button]]]:
    """Render Telegram text and inline buttons for review inbox."""
    flags_text = ", ".join(i.flags) if i.flags else "none"
    text = f"Review needed:\nTitle: {i.title}\nDomain: {i.domain}\nFlags: {flags_text}"
    buttons = [
        [
            Button(text="Keep", data=f"keep:{i.id}"),
            Button(text="Discard", data=f"drop:{i.id}"),
        ]
    ]
    return text, buttons


async def decide(session: AsyncSession, item_id: int, keep: bool) -> None:
    """Apply review decision to an item and record the audit decision."""
    stmt = select(Item).where(Item.id == item_id)
    res = await session.execute(stmt)
    item = res.scalar_one_or_none()

    decision_str = "keep" if keep else "drop"
    if item is not None:
        if keep:
            item.status = "new"
            current_flags = list(item.flags or [])
            if "owner_approved" not in current_flags:
                current_flags.append("owner_approved")
            item.flags = current_flags
        else:
            item.status = "filtered_out"

    decision_record = ReviewDecision(item_id=item_id, decision=decision_str)
    session.add(decision_record)
    await session.flush()
