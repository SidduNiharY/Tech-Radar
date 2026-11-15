from __future__ import annotations

from datetime import UTC, datetime

from techradar.jarvis.greeting import (
    is_quiet_hours,
    prepare_greeting,
    run_prepare_greeting,
    suggest_next_actions,
)


def test_is_quiet_hours_overnight_span():
    # Quiet hours: 22:00 to 07:00
    # Inside quiet hours (evening)
    dt_2200 = datetime(2026, 11, 15, 22, 0, tzinfo=UTC)
    assert is_quiet_hours(dt_2200, 22, 7) is True

    dt_2359 = datetime(2026, 11, 15, 23, 59, tzinfo=UTC)
    assert is_quiet_hours(dt_2359, 22, 7) is True

    # Inside quiet hours (early morning)
    dt_0000 = datetime(2026, 11, 15, 0, 0, tzinfo=UTC)
    assert is_quiet_hours(dt_0000, 22, 7) is True

    dt_0430 = datetime(2026, 11, 15, 4, 30, tzinfo=UTC)
    assert is_quiet_hours(dt_0430, 22, 7) is True

    dt_0659 = datetime(2026, 11, 15, 6, 59, tzinfo=UTC)
    assert is_quiet_hours(dt_0659, 22, 7) is True

    # Outside quiet hours
    dt_0700 = datetime(2026, 11, 15, 7, 0, tzinfo=UTC)
    assert is_quiet_hours(dt_0700, 22, 7) is False

    dt_1200 = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)
    assert is_quiet_hours(dt_1200, 22, 7) is False

    dt_2159 = datetime(2026, 11, 15, 21, 59, tzinfo=UTC)
    assert is_quiet_hours(dt_2159, 22, 7) is False


def test_is_quiet_hours_same_day():
    # Quiet hours within the same day: 13:00 to 15:00
    dt_1259 = datetime(2026, 11, 15, 12, 59, tzinfo=UTC)
    assert is_quiet_hours(dt_1259, 13, 15) is False

    dt_1300 = datetime(2026, 11, 15, 13, 0, tzinfo=UTC)
    assert is_quiet_hours(dt_1300, 13, 15) is True

    dt_1430 = datetime(2026, 11, 15, 14, 30, tzinfo=UTC)
    assert is_quiet_hours(dt_1430, 13, 15) is True

    dt_1500 = datetime(2026, 11, 15, 15, 0, tzinfo=UTC)
    assert is_quiet_hours(dt_1500, 13, 15) is False


def test_suggest_next_actions_max_three():
    # Verify at most 3 suggestions returned across diverse combinations
    scenarios = [
        (0, 0, None),
        (5, 10, "GATE CS"),
        (1, 1, "RBI Grade B"),
        (0, 20, None),
        (10, 0, "UPSC CSE"),
        (100, 50, "ISRO Scientist"),
    ]
    for streak, due, exam in scenarios:
        actions = suggest_next_actions(streak, due, exam)
        assert len(actions) <= 3, (
            f"Expected <= 3 actions, got {len(actions)} for {streak}, {due}, {exam}"
        )
        assert all(isinstance(a, str) and len(a) > 0 for a in actions)


def test_suggest_next_actions_prioritization():
    # Due cards priority
    actions_cards = suggest_next_actions(streak_days=3, due_cards=8, next_exam="GATE CS")
    assert any("8 flashcards due" in a for a in actions_cards)
    assert any("GATE CS" in a for a in actions_cards)
    assert any("3-days study streak" in a for a in actions_cards)

    # Singular flashcard
    actions_1_card = suggest_next_actions(streak_days=1, due_cards=1, next_exam=None)
    assert any("1 flashcard due" in a for a in actions_1_card)
    assert any("1-day study streak" in a for a in actions_1_card)

    # Zero streak kickoff suggestion
    actions_zero_streak = suggest_next_actions(streak_days=0, due_cards=0, next_exam=None)
    assert any("start your daily study streak" in a.lower() for a in actions_zero_streak)


def test_prepare_greeting_time_of_day():
    # Morning
    dt_morning = datetime(2026, 11, 15, 8, 30, tzinfo=UTC)
    greeting_m = prepare_greeting("Alice", dt_morning, 5, 10, "GATE CS")
    assert greeting_m.startswith("Good morning, Alice.")
    assert "Three things for you today:" in greeting_m
    assert "10 flashcards" in greeting_m
    assert "GATE CS" in greeting_m

    # Afternoon
    dt_afternoon = datetime(2026, 11, 15, 14, 0, tzinfo=UTC)
    greeting_a = prepare_greeting("Bob", dt_afternoon, 0, 0, None)
    assert greeting_a.startswith("Good afternoon, Bob.")

    # Evening
    dt_evening = datetime(2026, 11, 15, 19, 15, tzinfo=UTC)
    greeting_e = prepare_greeting("Carol", dt_evening, 2, 4, "IBPS PO")
    assert greeting_e.startswith("Good evening, Carol.")

    # Night / early morning
    dt_night = datetime(2026, 11, 15, 23, 30, tzinfo=UTC)
    greeting_n = prepare_greeting("Dan", dt_night, 1, 0, None)
    assert greeting_n.startswith("Hello, Dan.")

    # Blank name fallback
    greeting_blank = prepare_greeting("   ", dt_morning, 0, 0, None)
    assert greeting_blank.startswith("Good morning, there.")

    # Compatibility alias check
    assert run_prepare_greeting("Alice", dt_morning, 5, 10, "GATE CS") == greeting_m
