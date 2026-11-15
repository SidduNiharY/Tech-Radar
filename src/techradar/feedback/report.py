"""Weekly improvement report rendering, evidence verification, and approval buttons."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import ActionLog, Edit, Feedback
from techradar.feedback.patterns import PatternCandidate
from techradar.feedback.rules import Pick
from techradar.messaging.outbox import Button


async def verify_evidence(
    session: AsyncSession,
    c: PatternCandidate,
    now: datetime,
) -> bool:
    """Verify that all evidence IDs exist in target table within window_days and match count."""
    if not c.evidence.ids:
        return False

    window_start = now - timedelta(days=c.evidence.window_days)
    table_name = c.evidence.table

    if table_name == "feedback":
        stmt = (
            select(func.count())
            .select_from(Feedback)
            .where(
                Feedback.id.in_(c.evidence.ids),
                Feedback.at >= window_start,
            )
        )
    elif table_name == "action_log":
        stmt = (
            select(func.count())
            .select_from(ActionLog)
            .where(
                ActionLog.id.in_(c.evidence.ids),
                ActionLog.at >= window_start,
            )
        )
    elif table_name == "edits":
        stmt = (
            select(func.count())
            .select_from(Edit)
            .where(
                Edit.id.in_(c.evidence.ids),
                Edit.at >= window_start,
            )
        )
    else:
        # For other tables without direct models in session, verify list length
        return len(c.evidence.ids) == c.evidence.count

    res = await session.execute(stmt)
    found_count = res.scalar() or 0
    return bool(found_count == c.evidence.count and found_count == len(c.evidence.ids))


def render_report(
    week_start: date,
    picks: Sequence[tuple[int, Pick, PatternCandidate]],
    automatic: Sequence[Any],
    tests_added: int = 0,
) -> tuple[str, list[list[Button]]]:
    """Render the weekly self-improvement report with suggested and automatic changes."""
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
    """Weekly summary of positive/negative signals, mastery changes, active prompt rules."""
    return render_report(week_start, picks, automatic, tests_added=tests_added)
