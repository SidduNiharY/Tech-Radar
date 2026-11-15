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


async def infer_skips(session: AsyncSession, day: date) -> int:
    """Infer skips for briefing items with no user action within 24 hours."""
    # Find all items presented on day from action_log or feedback
    start_dt = datetime.combine(day, datetime.min.time(), tzinfo=UTC)
    end_dt = start_dt + timedelta(days=1)

    # Gather actions in the 24h window
    actions_stmt = select(ActionLog.target, ActionLog.kind).where(
        ActionLog.at >= start_dt, ActionLog.at < end_dt + timedelta(days=1)
    )
    res = await session.execute(actions_stmt)
    actions_by_target: dict[str, set[str]] = {}
    for target, kind in res.all():
        actions_by_target.setdefault(target, set()).add(kind)

    # Gather feedback in the window
    fb_stmt = select(Feedback.target_kind, Feedback.target_id).where(Feedback.day == day)
    fb_res = await session.execute(fb_stmt)
    feedback_targets = {f"item:{target_id}" for _, target_id in fb_res.all()}

    inferred = 0
    # For every presented item without open, save, or feedback, log a skip
    presented_stmt = select(ActionLog.target, ActionLog.topic, ActionLog.source).where(
        ActionLog.kind == "present",
        ActionLog.at >= start_dt,
        ActionLog.at < end_dt,
    )
    pres_res = await session.execute(presented_stmt)
    for target, topic, source in pres_res.all():
        user_actions = actions_by_target.get(target, set())
        has_interaction = bool(
            user_actions.intersection({"open", "save", "ask", "follow_up"})
            or target in feedback_targets
        )
        if not has_interaction and "skip" not in user_actions:
            await log_action(
                session,
                kind="skip",
                target=target,
                topic=topic,
                source=source,
                now=end_dt,
            )
            inferred += 1

    return inferred
