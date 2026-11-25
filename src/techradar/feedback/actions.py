"""Action logging for implicit feedback tracking."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import ActionLog, Feedback


async def log_action(
    session: AsyncSession,
    kind: str,
    target: str,
    *,
    topic: str | None = None,
    source: str | None = None,
    mode: str | None = None,
    now: datetime | None = None,
) -> None:
    """Log user or system activity action for implicit feedback signals."""
    ts = now or datetime.now(UTC)
    entry = ActionLog(
        kind=kind,
        target=target,
        topic=topic,
        source=source,
        mode=mode,
        at=ts,
    )
    session.add(entry)
    await session.flush()


FOLLOW_UP_WINDOW = timedelta(minutes=10)
_FOLLOW_UP_WORDS = (
    ("example", "follow:example"),
    ("simpler", "follow:simpler"),
    ("why", "follow:why"),
)


def follow_up_class(question: str) -> str:
    """Which kind of follow-up the owner's own question is: example, simpler, why or other."""
    low = question.lower()
    return next((tag for word, tag in _FOLLOW_UP_WORDS if word in low), "follow:other")


async def note_ask(
    session: AsyncSession,
    *,
    chat_id: int,
    question: str,
    mode: str | None,
    now: datetime,
) -> None:
    """Log an `ask`; one within 10 minutes of my previous answer is a `follow_up`.

    The follow-up's `target` is `answer:<previous id>`; its `topic` holds the class of my own
    words (never the text), which the nightly pattern rules count. Call it for the owner only.
    """
    from techradar.db.models import Answer

    prev = (
        await session.execute(
            select(Answer.id)
            .where(Answer.chat_id == chat_id, Answer.created_at >= now - FOLLOW_UP_WINDOW)
            .order_by(Answer.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if prev is not None:
        await log_action(
            session,
            "follow_up",
            f"answer:{prev}",
            topic=follow_up_class(question),
            mode=mode,
            now=now,
        )
    await log_action(session, "ask", f"ask:{chat_id}", mode=mode, now=now)


async def infer_skips(session: AsyncSession, day: date) -> int:
    """Nightly: a briefing story of `day` with no open, save, button or take for 24 hours is a skip.

    Stories come from that day's `briefings.items`. Each story is judged once: an existing
    `skip` for it is never doubled.
    """
    from techradar.db.models import Briefing

    briefing = (
        await session.execute(select(Briefing).where(Briefing.date == day))
    ).scalar_one_or_none()
    if briefing is None or not briefing.items:
        return 0
    start = briefing.sent_at
    end = start + timedelta(hours=24)
    acted = {
        t
        for (t,) in (
            await session.execute(
                select(ActionLog.target).where(
                    ActionLog.kind.in_(("open", "save", "skip")), ActionLog.at >= start
                )
            )
        ).all()
    }
    voted = {
        f"story:{i}"
        for (i,) in (
            await session.execute(
                select(Feedback.target_id).where(
                    Feedback.target_kind == "digest_item", Feedback.at >= start, Feedback.at < end
                )
            )
        ).all()
    }
    inferred = 0
    for it in briefing.items:
        cid = str(it.get("cluster_id", ""))
        target = f"story:{cid}"
        if not cid.isdigit() or target in acted or target in voted:
            continue
        keys = it.get("topic_keys") or []
        sources = it.get("source_keys") or []
        await log_action(
            session,
            "skip",
            target,
            topic=keys[0] if keys else None,
            source=sources[0] if sources else None,
            now=end,
        )
        inferred += 1
    return inferred
