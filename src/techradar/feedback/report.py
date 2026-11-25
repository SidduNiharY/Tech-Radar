"""Weekly improvement report: evidence check, layout, and the weekly job body (Phase 11 Task 6).

SEC: SEC-17, SEC-18, SEC-48.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime, timedelta
from typing import Any

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import (
    ActionLog,
    Answer,
    Edit,
    Feedback,
    ImprovementLog,
    ImprovementReport,
    Mistake,
    PreferencePair,
    StudySession,
)
from techradar.feedback.approval import store_proposals
from techradar.feedback.patterns import (
    PatternCandidate,
    StyleProposal,
    WeightProposal,
    find_patterns,
)
from techradar.feedback.rules import Pick, choose_and_word
from techradar.llm.roles import Role
from techradar.messaging.outbox import Button, enqueue_message

# D46: the least evidence each rule needs before it may be suggested.
MIN_COUNT = {
    "source": 5,
    "sequence": 5,
    "confusion": 5,
    "mistakes": 3,
    "time": 7,
    "edit": 5,
    "pairs": 5,
}

# table name -> (model, id column, time column)
_TABLES: dict[str, tuple[Any, Any, Any]] = {
    "feedback": (Feedback, Feedback.id, Feedback.at),
    "action_log": (ActionLog, ActionLog.id, ActionLog.at),
    "edits": (Edit, Edit.id, Edit.at),
    "mistakes": (Mistake, Mistake.id, Mistake.created_at),
    "study_sessions": (StudySession, StudySession.id, StudySession.started_at),
    "preference_pairs": (PreferencePair, PreferencePair.id, PreferencePair.answered_at),
    "answers": (Answer, Answer.id, Answer.created_at),
}
MAX_IDS = 200


def _meets_threshold(c: PatternCandidate) -> bool:
    ev = c.evidence
    if c.kind == "frequency":
        return ev.total is not None and ev.total >= 10 and ev.count / ev.total > 0.70
    return ev.count >= MIN_COUNT.get(c.kind, 1)


async def verify_evidence(
    session: AsyncSession,
    c: PatternCandidate,
    now: datetime,
    owner_chat_id: int | None = None,
) -> bool:
    """Code re-checks the evidence: every id exists in its table, inside the window, and the
    count matches the rows found and meets the D46 threshold (SEC-48).
    """
    ev = c.evidence
    if not ev.ids or len(set(ev.ids)) != len(ev.ids) or not _meets_threshold(c):
        return False
    table = _TABLES.get(ev.table)
    if table is None:  # an unknown table (or quiz_attempts, which nothing proposes from) fails
        return False
    model, id_col, time_col = table
    stmt = (
        select(func.count())
        .select_from(model)
        .where(id_col.in_(ev.ids), time_col >= now - timedelta(days=ev.window_days))
    )
    if ev.table == "answers":  # only my own asks count, never a study group's
        if owner_chat_id is None:
            return False
        stmt = stmt.where(Answer.chat_id == owner_chat_id)
    found = (await session.execute(stmt)).scalar() or 0
    if found != len(ev.ids):
        return False
    # ids are capped at 200; a larger count is allowed only when the cap was hit
    return ev.count == len(ev.ids) or (len(ev.ids) == MAX_IDS and ev.count > MAX_IDS)


def describe(c: PatternCandidate) -> str:
    """What approving does, written from the stored proposal (not from the model's wording)."""
    p = c.proposal
    if isinstance(p, StyleProposal):
        return f"Rule: {p.mode.value if p.mode else 'all modes'}: {p.field} = {p.value}"
    if isinstance(p, WeightProposal):
        return f"Weight: {p.key} to {p.target}"
    return f"Make: {p.kind.replace('_', ' ')} on {p.subject}"


def render_report(
    week_start: date,
    picks: Sequence[tuple[int, Pick, PatternCandidate]],
    automatic: Sequence[Any],
    tests_added: int = 0,
) -> tuple[str, list[list[Button]]]:
    """Render the weekly report as in 06 B5, with Approve and Ignore buttons per suggestion."""
    lines: list[str] = ["🔧 Weekly improvement report"]
    buttons: list[list[Button]] = []

    if picks:
        lines.append("\nChanges I suggest (tap to approve):")
        for i, (prop_id, pick, cand) in enumerate(picks, 1):
            if cand.evidence.total is not None:
                detail = f"{cand.evidence.count} of {cand.evidence.total}"
            else:
                detail = f"{cand.evidence.count} times in {cand.evidence.window_days} days"
            lines.append(f"{i}. {pick.wording}: {detail}")
            lines.append(f"   {describe(cand)}")
            buttons.append(
                [
                    Button(text=f"Approve {i}", data=f"rule_ok:{prop_id}"),
                    Button(text=f"Ignore {i}", data=f"rule_no:{prop_id}"),
                ]
            )

    if automatic or tests_added > 0:
        lines.append("\nDone automatically (within limits):")
        for auto in automatic:
            if isinstance(auto, str):
                lines.append(f"• {auto}")
            elif hasattr(auto, "key"):
                lines.append(f"• Adjusted weight for {auto.key}")
            elif isinstance(auto, dict) and "key" in auto:
                lines.append(f"• Adjusted weight for {auto['key']}")
        if tests_added > 0:
            lines.append(f"• {tests_added} bad answers saved as new tests")

    lines.append("\nUndo anything: /improvements")
    return "\n".join(lines), buttons


def render_feedback_report(
    week_start: date,
    picks: Sequence[tuple[int, Pick, PatternCandidate]],
    automatic: Sequence[Any],
    tests_added: int = 0,
) -> tuple[str, list[list[Button]]]:
    """Alias kept for the first run's callers."""
    return render_report(week_start, picks, automatic, tests_added=tests_added)


class WeeklyResult(BaseModel):
    week_start: date
    suggestions: int = 0
    automatic: int = 0
    sent: bool = False
    skipped_reason: str | None = None


def week_start_of(day: date) -> date:
    """The Monday of the week that `day` is in."""
    return day - timedelta(days=day.weekday())


async def run_weekly_report(
    session: AsyncSession,
    completer: Any,
    embedder: Any,
    *,
    now: datetime,
    today: date,
    owner_chat_id: int,
    role: Role = Role.WORKER,
) -> WeeklyResult:
    """The weekly job body: find, re-check, let the model pick and word at most 3, send.

    Once per week (the `week_start` is unique). Every suggestion has its evidence re-verified
    in code first; the model sees only cleaned candidate summaries and returns indices and
    wordings. Rows stay `proposed` until the owner taps Approve (SEC-48).
    """
    week = week_start_of(today)
    if (
        await session.execute(
            select(ImprovementReport.id).where(ImprovementReport.week_start == week)
        )
    ).scalar_one_or_none() is not None:
        return WeeklyResult(week_start=week, skipped_reason="already_sent")

    found = await find_patterns(session, embedder, now, owner_chat_id=owner_chat_id)
    verified = [c for c in found if await verify_evidence(session, c, now, owner_chat_id)]
    picks = await choose_and_word(completer, verified, role) if verified else []
    chosen = [(p, verified[p.candidate_index]) for p in picks]

    report = ImprovementReport(week_start=week, text="")
    session.add(report)
    await session.flush()
    prop_ids = await store_proposals(session, chosen, now=now, report_id=report.id)
    # a dropped proposal (invalid style rule) also drops its pick
    shown = [(pid, p, c) for pid, (p, c) in zip(prop_ids, chosen, strict=False)]

    since = now - timedelta(days=7)
    logs = (
        (
            await session.execute(
                select(ImprovementLog).where(
                    ImprovementLog.automatic.is_(True), ImprovementLog.at >= since
                )
            )
        )
        .scalars()
        .all()
    )
    tests_added = sum(1 for r in logs if r.key.startswith("regression:"))
    automatic = [r for r in logs if not r.key.startswith("regression:")]

    if not shown and not automatic and tests_added == 0:
        report.text = "nothing to report"
        return WeeklyResult(week_start=week, skipped_reason="nothing_to_report")

    text, buttons = render_report(week, shown, automatic, tests_added=tests_added)
    report.text = text
    report.sent_at = now
    await enqueue_message(
        session,
        chat_id=owner_chat_id,
        text=text,
        purpose="improvement_report",
        buttons=buttons or None,
        ref_id=report.id,
    )
    return WeeklyResult(
        week_start=week, suggestions=len(shown), automatic=len(automatic), sent=True
    )
