from __future__ import annotations

from techradar.practice.fsrs import Card, State
from techradar.practice.mcq import MCQDraft
from techradar.practice.quiz import (
    DailyPracticeLimits,
    MistakesNotebook,
    TwoModelKeyChecker,
)


def _make_sample_draft(answer_index: int = 1) -> MCQDraft:
    return MCQDraft(
        question="Which organisation publishes the Wholesale Price Index in India?",
        options=[
            "Reserve Bank of India",
            "Office of Economic Adviser",
            "NITI Aayog",
            "Ministry of Finance",
        ],
        answer_index=answer_index,
        explanation="Office of Economic Adviser under DPIIT publishes WPI.",
    )


def test_checker_disagreement_drops_mcq():
    draft = _make_sample_draft(answer_index=1)
    # Checker selects index 2 (NITI Aayog) instead of 1 (Office of Economic Adviser)
    assert not TwoModelKeyChecker.verify_mcq_key(draft, checker_answer_index=2)


def test_checker_agreement_keeps_mcq():
    draft = _make_sample_draft(answer_index=1)
    # Checker agrees on index 1
    assert TwoModelKeyChecker.verify_mcq_key(draft, checker_answer_index=1)


def test_daily_limits_cap_new_and_reviews():
    # 25 new cards and 100 review cards
    new_cards = [Card(state=State.NEW) for _ in range(25)]
    review_cards = [Card(state=State.REVIEW) for _ in range(100)]
    all_due = new_cards + review_cards

    # Standard mode: max 10 new, max 40 reviews
    standard_filtered = DailyPracticeLimits.filter_due_cards(all_due, is_final_mode=False)
    standard_new = [c for c in standard_filtered if c.state == State.NEW]
    standard_reviews = [c for c in standard_filtered if c.state != State.NEW]
    assert len(standard_new) == 10
    assert len(standard_reviews) == 40
    assert len(standard_filtered) == 50

    # Instance call works identically
    limits = DailyPracticeLimits()
    instance_filtered = limits.filter_due_cards(all_due, is_final_mode=False)
    assert len(instance_filtered) == 50

    # Final 30 days exam mode: max 10 new, max 80 reviews
    final_filtered = DailyPracticeLimits.filter_due_cards(all_due, is_final_mode=True)
    final_new = [c for c in final_filtered if c.state == State.NEW]
    final_reviews = [c for c in final_filtered if c.state != State.NEW]
    assert len(final_new) == 10
    assert len(final_reviews) == 80
    assert len(final_filtered) == 90


def test_mistakes_notebook_records_and_retrieves():
    notebook = MistakesNotebook()

    notebook.record_mistake(
        user_id=101,
        question_id="mcq_eco_42",
        chosen_option=0,
        correct_option=1,
        explanation="Office of Economic Adviser publishes WPI, not RBI.",
    )

    notebook.record_mistake(
        user_id=101,
        question_id="mcq_polity_15",
        chosen_option=2,
        correct_option=3,
        explanation="Article 32 provides right to constitutional remedies.",
    )

    notebook.record_mistake(
        user_id=202,
        question_id="mcq_gate_cs_01",
        chosen_option=1,
        correct_option=0,
        explanation="Dijkstra algorithm does not handle negative edge weights.",
    )

    user_101_mistakes = notebook.get_mistakes(101)
    assert len(user_101_mistakes) == 2
    assert user_101_mistakes[0].question_id == "mcq_eco_42"
    assert user_101_mistakes[0].chosen_option == 0
    assert user_101_mistakes[0].correct_option == 1
    assert "WPI" in user_101_mistakes[0].explanation

    assert user_101_mistakes[1].question_id == "mcq_polity_15"
    assert user_101_mistakes[1].correct_option == 3

    # Also test index access / get_user_mistakes
    assert notebook.get_user_mistakes(101) == user_101_mistakes
    assert notebook[101] == user_101_mistakes

    user_202_mistakes = notebook.get_mistakes(202)
    assert len(user_202_mistakes) == 1
    assert user_202_mistakes[0].question_id == "mcq_gate_cs_01"

    # Unknown user has empty list
    assert notebook.get_mistakes(999) == []
