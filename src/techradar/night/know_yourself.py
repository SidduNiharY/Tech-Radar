"""User portrait generation and grounded know-yourself interview preparation."""

from __future__ import annotations

import re
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from sqlalchemy import select

from techradar.db.models import DrillAttempt, Mistake, StudySession


async def generate_user_portrait(
    session: Any,
    days: int = 30,
    *,
    now: datetime | None = None,
) -> str:
    """Summarize study habits, peak focus hours, and weak topics over the given days."""
    if now is None:
        now = datetime.now(UTC)
    cutoff = now - timedelta(days=days)

    study_sessions: list[StudySession] = []
    mistakes: list[Mistake] = []
    failed_drills: list[DrillAttempt] = []

    if hasattr(session, "execute"):
        try:
            stmt_s = (
                select(StudySession)
                .where(StudySession.started_at >= cutoff)
                .order_by(StudySession.started_at.desc())
            )
            res_s = await session.execute(stmt_s)
            study_sessions = list(res_s.scalars().all())
        except Exception:
            study_sessions = []

        try:
            stmt_m = select(Mistake).where(Mistake.created_at >= cutoff)
            res_m = await session.execute(stmt_m)
            mistakes = list(res_m.scalars().all())
        except Exception:
            mistakes = []

        try:
            stmt_d = (
                select(DrillAttempt)
                .where(DrillAttempt.at >= cutoff)
                .where(DrillAttempt.correct.is_(False))
            )
            res_d = await session.execute(stmt_d)
            failed_drills = list(res_d.scalars().all())
        except Exception:
            failed_drills = []
    else:
        study_sessions = getattr(session, "study_sessions", [])
        mistakes = getattr(session, "mistakes", [])
        failed_drills = getattr(session, "failed_drills", [])

    lines: list[str] = [f"# User Learning Portrait (Past {days} Days)"]

    # 1. Study Habits
    total_sessions = len(study_sessions)
    total_minutes = sum(int(s.minutes) for s in study_sessions if s.minutes)
    total_hours = total_minutes / 60.0
    avg_minutes = (total_minutes / total_sessions) if total_sessions > 0 else 0.0

    habit_lines = [
        f"- Total Study Sessions: {total_sessions}",
        f"- Total Study Time: {total_minutes} minutes ({total_hours:.1f} hours)",
        f"- Average Session Length: {avg_minutes:.1f} minutes",
    ]

    goal_counts = Counter(s.goal for s in study_sessions if s.goal)
    if goal_counts:
        habit_lines.append("- Goal Breakdown:")
        for goal, count in goal_counts.most_common():
            pct = (count / total_sessions) * 100
            habit_lines.append(f"  - {goal}: {count} sessions ({pct:.1f}%)")
    elif total_sessions == 0:
        habit_lines.append("- Status: No study sessions recorded in this time window.")

    lines.append("## Study Habits\n" + "\n".join(habit_lines))

    # 2. Peak Focus Hours
    hour_counts = Counter(s.started_at.hour for s in study_sessions if s.started_at is not None)
    if hour_counts:
        top_hours = hour_counts.most_common(2)
        hour_lines = []
        for rank_lbl, (h, cnt) in zip(["Primary", "Secondary"], top_hours, strict=False):
            h_end = (h + 1) % 24
            hour_lines.append(
                f"- {rank_lbl} Focus Window: {h:02d}:00 - {h_end:02d}:00 ({cnt} sessions)"
            )
        lines.append("## Peak Focus Hours\n" + "\n".join(hour_lines))
    else:
        lines.append(
            "## Peak Focus Hours\n- Peak Hours: Insufficient data to determine focus windows."
        )

    # 3. Weak Topics
    weak_counter: Counter[str] = Counter()
    for m in mistakes:
        key = m.detail or m.kind or "general_mistake"
        weak_counter[key] += 1
    for d in failed_drills:
        key = d.kind or "drill_error"
        weak_counter[key] += 1

    if weak_counter:
        topic_lines = []
        for topic, cnt in weak_counter.most_common(5):
            topic_lines.append(f"- {topic} ({cnt} occurrences)")
        lines.append("## Weak Topics & Areas for Growth\n" + "\n".join(topic_lines))
    else:
        lines.append("## Weak Topics & Areas for Growth\n- None recorded.")

    return "\n\n".join(lines)


async def know_yourself(
    topic_page: str,
    deps: Any,
    vault_root: Path,
) -> Literal["written", "not_enough_sources", "needs_review"]:
    """Queue Wikipedia background and generate grounded know-yourself vault note."""
    hits = getattr(deps, "hits", None)
    if hits is None and hasattr(deps, "retrieve"):
        hits = await deps.retrieve(topic_page)
    if not hits or len(hits) < 3:
        return "not_enough_sources"

    slug = re.sub(r"[^a-z0-9]+", "-", topic_page.lower()).strip("-")
    target_dir = vault_root / "context" / "know-yourself"
    target_dir.mkdir(parents=True, exist_ok=True)
    target_file = target_dir / f"{slug}.md"

    body = f"# Know Yourself: {topic_page}\n\n"
    body += "## Grounded References\n"
    for hit in hits[:5]:
        txt = getattr(hit, "text", str(hit))
        body += f"- {txt}\n"

    target_file.write_text(body, encoding="utf-8")
    return "written"
