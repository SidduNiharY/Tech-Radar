from __future__ import annotations

from datetime import datetime


def is_quiet_hours(
    now_dt: datetime,
    start_hour: int = 22,
    end_hour: int = 7,
) -> bool:
    """Determine whether the specified time falls within quiet hours.

    When start_hour > end_hour, quiet hours span across midnight (e.g. 22:00 to 07:00).
    When start_hour < end_hour, quiet hours occur within the same calendar day.
    """
    hour = now_dt.hour
    if start_hour > end_hour:
        return hour >= start_hour or hour < end_hour
    elif start_hour < end_hour:
        return start_hour <= hour < end_hour
    return False


def suggest_next_actions(
    streak_days: int,
    due_cards: int,
    next_exam: str | None,
) -> list[str]:
    """Suggest up to 3 prioritized, concise next actions for the user."""
    suggestions: list[str] = []

    # 1. Due flashcards (high priority spaced repetition)
    if due_cards > 0:
        noun = "flashcard" if due_cards == 1 else "flashcards"
        suggestions.append(f"Review {due_cards} {noun} due for spaced repetition.")

    # 2. Upcoming exam preparation
    if next_exam and next_exam.strip():
        suggestions.append(f"Study priority syllabus topics for {next_exam.strip()}.")

    # 3. Streak continuation or kickoff
    if streak_days > 0:
        noun = "day" if streak_days == 1 else "days"
        suggestions.append(
            f"Keep your {streak_days}-{noun} study streak going with a quick session."
        )
    else:
        suggestions.append("Kickstart your daily study streak with a short practice session.")

    # 4. Fallback suggestions to ensure active actionable guidance
    if len(suggestions) < 3:
        suggestions.append("Check today's news and economic updates in your briefing.")
    if len(suggestions) < 3:
        suggestions.append("Explore a new chapter in your reading library.")

    return suggestions[:3]


def _time_salutation(hour: int) -> str:
    """Determine the appropriate time-of-day greeting."""
    if 5 <= hour < 12:
        return "Good morning"
    elif 12 <= hour < 17:
        return "Good afternoon"
    elif 17 <= hour < 22:
        return "Good evening"
    return "Hello"


def prepare_greeting(
    user_name: str,
    now_dt: datetime,
    streak_days: int,
    due_cards: int,
    next_exam: str | None,
) -> str:
    """Prepare a spoken or displayed greeting incorporating user status and suggestions."""
    name = user_name.strip() or "there"
    salutation = _time_salutation(now_dt.hour)
    header = f"{salutation}, {name}."

    actions = suggest_next_actions(streak_days, due_cards, next_exam)
    if not actions:
        return f"{header} All caught up today. What would you like to explore?"

    count_words = {1: "One thing", 2: "Two things", 3: "Three things"}
    count_phrase = count_words.get(len(actions), f"{len(actions)} things")
    items_text = " ".join(f"{i + 1}. {act}" for i, act in enumerate(actions))
    return f"{header} {count_phrase} for you today: {items_text} What would you like to start with?"


# Compatibility alias for implementations.md
run_prepare_greeting = prepare_greeting

__all__ = [
    "is_quiet_hours",
    "prepare_greeting",
    "run_prepare_greeting",
    "suggest_next_actions",
]
