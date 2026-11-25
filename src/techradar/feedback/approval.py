"""Proposals, the owner's approval, undo and the active rules (Phase 11 Task 6).

Only the owner's tap changes anything here, and only for a row that is still `proposed`. A
proposal row is made from a pattern candidate's own fields, never from model text or from
content, and a style rule is re-validated as a `StyleRule` at approval (SEC-48, AGENTS rule 7).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Literal, get_args

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import ImprovementLog, PreferenceRule, Revision, Weight
from techradar.feedback.patterns import (
    Mode,
    PatternCandidate,
    StyleProposal,
    WeightProposal,
)
from techradar.feedback.rules import Pick, StyleField, StyleRule
from techradar.feedback.weights import bounded, safe_key
from techradar.messaging.outbox import Button
from techradar.planner.sessions import Goal

STYLE_FIELDS = frozenset(get_args(StyleField))
ApproveResult = Literal["approved", "not_found", "not_proposed", "invalid"]
UndoResult = Literal["undone", "not_found", "already_undone", "not_undoable"]
_SAFE_TEXT = re.compile(r"[^A-Za-z0-9 :._-]")


def _clean(text: str, limit: int = 120) -> str:
    return _SAFE_TEXT.sub("", text)[:limit].strip()


async def store_proposals(
    session: AsyncSession,
    picks: Sequence[tuple[Pick, PatternCandidate]],
    *,
    now: datetime,
    report_id: int | None = None,
) -> list[int]:
    """Store each pick's own candidate proposal as a `proposed` row; return the row ids.

    The row's field and value come from the candidate (plain code). The model's wording is not
    stored here at all. A style proposal that is not a valid `StyleRule` is dropped.
    """
    ids: list[int] = []
    for _, cand in picks:
        prop = cand.proposal
        if isinstance(prop, StyleProposal):
            try:
                rule = StyleRule(mode=prop.mode, field=prop.field, value=prop.value)  # type: ignore[arg-type]
            except ValidationError:
                continue
            mode = rule.mode.value if rule.mode else None
            field, value = rule.field, rule.value
        elif isinstance(prop, WeightProposal):
            mode, field, value = None, f"weight_{prop.kind}", prop.key[:200]
        else:
            mode, field, value = None, f"content_{prop.kind}", safe_key(prop.subject, 120)
        row = PreferenceRule(
            mode=mode,
            field=field,
            value=value,
            evidence={
                "evidence": cand.evidence.model_dump(),
                "proposal": prop.model_dump(mode="json"),
                "candidate_kind": cand.kind,
            },
            status="proposed",
            proposed_at=now,
            report_id=report_id,
        )
        session.add(row)
        await session.flush()
        ids.append(row.id)
    return ids


async def active_style_rules(session: AsyncSession, mode: Mode | None = None) -> list[StyleRule]:
    """The active style rules: global ones, plus the ones of `mode`. Invalid rows are skipped."""
    rows = (
        await session.execute(
            select(PreferenceRule)
            .where(PreferenceRule.status == "active", PreferenceRule.field.in_(STYLE_FIELDS))
            .order_by(PreferenceRule.id)
        )
    ).scalars()
    out: list[StyleRule] = []
    for r in rows:
        if r.mode is not None and (mode is None or r.mode != mode.value):
            continue
        try:
            out.append(
                StyleRule(
                    mode=Mode(r.mode) if r.mode else None,
                    field=r.field,  # type: ignore[arg-type]
                    value=r.value,
                )
            )
        except ValidationError, ValueError:
            continue
    return out


async def ignore_proposal(session: AsyncSession, rule_id: int) -> bool:
    """The owner ignores a proposal. Only a `proposed` row changes."""
    row = (
        await session.execute(
            select(PreferenceRule).where(PreferenceRule.id == rule_id).with_for_update()
        )
    ).scalar_one_or_none()
    if row is None or row.status != "proposed":
        return False
    row.status = "ignored"
    await session.flush()
    return True


async def _weight_row(session: AsyncSession, kind: str, key: str) -> Weight | None:
    return (
        await session.execute(select(Weight).where(Weight.kind == kind, Weight.key == key))
    ).scalar_one_or_none()


async def approve_proposal(session: AsyncSession, rule_id: int, now: datetime) -> ApproveResult:
    """The owner approves one proposal. Style: an active rule. Weight: a bounded weight.

    Content: queues its job when one exists. Each approval writes an `automatic=false` log row.
    """
    row = (
        await session.execute(
            select(PreferenceRule).where(PreferenceRule.id == rule_id).with_for_update()
        )
    ).scalar_one_or_none()
    if row is None:
        return "not_found"
    if row.status != "proposed":
        return "not_proposed"
    stored = row.evidence.get("proposal", {})

    if row.field in STYLE_FIELDS:
        try:
            rule = StyleRule(
                mode=Mode(row.mode) if row.mode else None,
                field=row.field,  # type: ignore[arg-type]
                value=row.value,
            )
        except ValidationError, ValueError:
            return "invalid"
        mode_value = rule.mode.value if rule.mode else None
        replaced = (
            (
                await session.execute(
                    select(PreferenceRule).where(
                        PreferenceRule.status == "active",
                        PreferenceRule.field == rule.field,
                        PreferenceRule.mode.is_(None)
                        if mode_value is None
                        else PreferenceRule.mode == mode_value,
                    )
                )
            )
            .scalars()
            .all()
        )
        for old in replaced:
            old.status = "undone"
        row.status = "active"
        row.approved_at = now
        session.add(
            ImprovementLog(
                kind="rule",
                key=f"rule:{row.id}",
                before={"status": "proposed", "replaced": [o.id for o in replaced]},
                after={
                    "status": "active",
                    "mode": mode_value,
                    "field": rule.field,
                    "value": rule.value,
                },
                automatic=False,
                at=now,
            )
        )
    elif row.field in ("weight_topic", "weight_source"):
        kind = "topic" if row.field == "weight_topic" else "source"
        try:
            target = float(stored["target"])
        except KeyError, TypeError, ValueError:
            return "invalid"
        w = await _weight_row(session, kind, row.value)
        before = w.value if w else 1.0
        new = bounded(target, floor=w.floor if w else None)
        if w:
            w.value, w.updated_at = new, now
        else:
            session.add(Weight(kind=kind, key=row.value, value=new, floor=None, updated_at=now))
        row.status = "active"
        row.approved_at = now
        session.add(
            ImprovementLog(
                kind="weight",
                key=row.value,
                before={"value": before},
                after={"value": new},
                automatic=False,
                at=now,
            )
        )
    elif row.field.startswith("content_"):
        queued = await _queue_content(session, row.field.removeprefix("content_"), row.value, now)
        row.status = "active"
        row.approved_at = now
        session.add(
            ImprovementLog(
                kind="content",
                key=f"{row.field}:{row.value}"[:200],
                before=None,
                after={"queued": queued},
                automatic=False,
                at=now,
            )
        )
    else:
        return "invalid"
    await session.flush()
    return "approved"


async def _queue_content(session: AsyncSession, kind: str, subject: str, now: datetime) -> bool:
    """Queue the approved content job. Only a focused revision exists today (a Revision row).

    WIRING(claude): `foundation_page` needs the phase 7 night writer and `comparison_card` the
    phase 3 cards-from-two-facts job; until they are wired the approval is only logged.
    """
    if kind != "focused_revision" or not subject:
        return False
    session.add(
        Revision(
            goal=Goal.CURRENT.value, topic=subject[:120], due_date=(now + timedelta(days=1)).date()
        )
    )
    return True


async def undo_change(session: AsyncSession, log_id: int, now: datetime) -> UndoResult:
    """Restore what a logged change replaced. Weights and rules (and search) can be undone."""
    log = (
        await session.execute(
            select(ImprovementLog).where(ImprovementLog.id == log_id).with_for_update()
        )
    ).scalar_one_or_none()
    if log is None:
        return "not_found"
    if log.undone_at is not None:
        return "already_undone"

    if log.kind in ("weight", "search"):
        if log.kind == "search":
            kind = "search"
        else:
            kind = "source" if log.key.startswith("source:") else "topic"
        w = await _weight_row(session, kind, log.key)
        before = (log.before or {}).get("value")
        if w is None or before is None:
            return "not_undoable"
        w.value, w.updated_at = float(before), now
    elif log.kind == "rule":
        rule_id = int(log.key.removeprefix("rule:"))
        rule = await session.get(PreferenceRule, rule_id)
        if rule is None:
            return "not_found"
        rule.status = "undone"
        for old_id in (log.before or {}).get("replaced", []):
            old = await session.get(PreferenceRule, old_id)
            if old is not None and old.status == "undone":
                old.status = "active"
    else:
        return "not_undoable"
    log.undone_at = now
    await session.flush()
    return "undone"


async def improvements_listing(session: AsyncSession) -> tuple[str, list[list[Button]]]:
    """`/improvements`: the active rules and the last 20 changes, each change with Undo."""
    rules = (
        (
            await session.execute(
                select(PreferenceRule)
                .where(PreferenceRule.status == "active", PreferenceRule.field.in_(STYLE_FIELDS))
                .order_by(PreferenceRule.id)
            )
        )
        .scalars()
        .all()
    )
    logs = (
        (
            await session.execute(
                select(ImprovementLog)
                .where(ImprovementLog.undone_at.is_(None), ImprovementLog.kind != "content")
                .order_by(ImprovementLog.id.desc())
                .limit(20)
            )
        )
        .scalars()
        .all()
    )

    lines = ["Active rules:"]
    if rules:
        lines += [f"• {r.mode or 'all'}: {r.field} = {r.value}" for r in rules]
    else:
        lines.append("• none yet")
    lines.append("\nLast changes:")
    buttons: list[list[Button]] = []
    for log in logs:
        who = "auto" if log.automatic else "approved"
        lines.append(f"{log.id}. {log.kind} {log.key[:40]} ({who})")
        buttons.append([Button(text=f"Undo {log.id}", data=f"undo:{log.id}")])
    if not logs:
        lines.append("• nothing yet")
    return "\n".join(lines), buttons
