from __future__ import annotations

from collections.abc import Sequence


def speak_daily_plan(goals: Sequence[str]) -> str:
    """Produce spoken text for daily study goals."""
    valid_goals = [g.strip() for g in goals if g.strip()]
    if not valid_goals:
        return "You have no study goals scheduled for today."

    if len(valid_goals) == 1:
        return f"You have 1 goal planned for today: {valid_goals[0]}."

    items_spoken = ". ".join(f"{idx + 1}, {goal}" for idx, goal in enumerate(valid_goals))
    return f"You have {len(valid_goals)} goals planned for today: {items_spoken}."
