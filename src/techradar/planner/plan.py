from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any

from techradar.planner.sessions import Goal

DEFAULT_EXAM_PRIORITY = [Goal.GOV, Goal.GATE]
DEFAULT_WEEKLY_TARGETS: dict[Goal, int] = {
    Goal.DEV: 600,
    Goal.GATE: 300,
    Goal.GOV: 420,
    Goal.CURRENT: 105,
    Goal.ENGLISH: 140,
}


def compose_plan(
    today: date,
    *,
    due_revisions: Sequence[Any],
    due_cards: int,
    quiz_ready: bool,
    minutes_this_week: Mapping[Goal, int],
    targets: Mapping[Goal, int],
    priority: Sequence[Goal],
    final_30_exam: str | None = None,
) -> list[str]:
    """Compose daily morning plan lines in strict priority order."""
    lines: list[str] = []

    # 1. Final 30 days exam alert
    if final_30_exam:
        lines.append(f"⏳ Final 30 days: {final_30_exam}")

    # 2. Daily Radar intake
    lines.append("📰 Radar (10–15 min)")

    # 3. Current affairs quiz
    if quiz_ready:
        lines.append("📝 Current affairs quiz: 10 MCQs")

    # 4. Spaced reviews due
    review_parts: list[str] = []
    if due_cards > 0:
        review_parts.append(f"{due_cards} flashcards")
    if len(due_revisions) > 0:
        review_parts.append(f"{len(due_revisions)} topic revisions")
    if review_parts:
        lines.append(f"🔁 Reviews due: {' + '.join(review_parts)}")

    # 5. Goal session with highest deficit
    # Determine candidate goals from priority (fallback to all target goals if priority empty)
    candidate_goals = list(priority) if priority else list(targets.keys())

    priority_map = {g: idx for idx, g in enumerate(priority)}

    def _deficit_score(g: Goal) -> tuple[float, int]:
        done = minutes_this_week.get(g, 0)
        tgt = targets.get(g, 1)
        deficit = 1.0 - (done / max(tgt, 1))
        # Round to 4 decimal places to prevent float precision noise on equal deficits
        rounded_deficit = round(deficit, 4)
        p_idx = priority_map.get(g, 999)
        return (-rounded_deficit, p_idx)

    chosen_goal = min(candidate_goals, key=_deficit_score)

    # Find first due revision topic for chosen goal
    first_topic = "next topic"
    for r in due_revisions:
        r_goal = getattr(r, "goal", None)
        if r_goal == chosen_goal.value or r_goal == chosen_goal:
            first_topic = getattr(r, "topic", "next topic")
            break

    goal_name = chosen_goal.name
    if final_30_exam:
        topic_str = first_topic if first_topic != "next topic" else "weak areas"
        lines.append(f"🎓 {goal_name}: revise {topic_str} (45 min)")
    else:
        lines.append(f"🎓 {goal_name}: {first_topic} (45 min)")

    # 6. English practice
    lines.append("🔤 English: 5 new words + 10 grammar questions")

    return lines
