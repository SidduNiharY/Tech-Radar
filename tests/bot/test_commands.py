"""Tests for interactive bot commands rendering (Phase 3).

SEC: SEC-20, SEC-26.
"""

from __future__ import annotations

import re

from techradar.bot.commands import (
    render_flashcard,
    render_grammar_card,
    render_quiz_card,
)
from techradar.practice.fsrs import Card
from techradar.practice.grammar import GrammarQuestion
from techradar.practice.mcq import MCQDraft

CALLBACK_PATTERN = re.compile(r"^[a-z_]{1,20}(:[0-9]{1,12}){1,2}$")


def _sample_mcq() -> MCQDraft:
    return MCQDraft(
        question="What is the primary repo rate in modern monetary policy?",
        options=[
            "Policy lending rate to commercial banks",
            "Overnight interbank deposit rate",
            "Government 10 year bond yield rate",
            "Consumer price index inflation rate target",
        ],
        answer_index=0,
        explanation="Repo rate is the rate at which the central bank lends to commercial banks.",
    )


def _sample_grammar_question() -> GrammarQuestion:
    return GrammarQuestion(
        id="gq_01",
        sentence_with_blank="Neither the manager nor the employees ___ aware of the delay.",
        options=["was", "were", "is", "are being"],
        correct_index=1,
        rule_explanation="When subjects are connected by neither... nor...",
        category="subject-verb-agreement",
    )


def test_render_quiz_card_formatting_and_buttons() -> None:
    draft = _sample_mcq()
    text, buttons = render_quiz_card(draft, question_index=1, total_questions=10)

    assert "Question 1/10:" in text
    assert draft.question in text
    assert f"A) {draft.options[0]}" in text
    assert f"B) {draft.options[1]}" in text
    assert f"C) {draft.options[2]}" in text
    assert f"D) {draft.options[3]}" in text

    all_buttons = [b for row in buttons for b in row]
    assert len(all_buttons) == 4
    for b in all_buttons:
        assert CALLBACK_PATTERN.match(b.data), f"Button data '{b.data}' does not match regex"

    assert [b.text for b in all_buttons] == ["A", "B", "C", "D"]
    assert [b.data for b in all_buttons] == [
        "quiz_ans:1:0",
        "quiz_ans:1:1",
        "quiz_ans:1:2",
        "quiz_ans:1:3",
    ]


def test_render_flashcard_initial_state() -> None:
    card = Card()
    text, buttons = render_flashcard(
        card=card,
        question_text="What is repo rate?",
        answer_text="The rate at which RBI lends money to commercial banks.",
        is_revealed=False,
    )

    assert "What is repo rate?" in text
    assert "RBI lends" not in text

    all_buttons = [b for row in buttons for b in row]
    assert len(all_buttons) == 1
    btn = all_buttons[0]
    assert btn.text == "Show Answer"
    assert CALLBACK_PATTERN.match(btn.data), f"Button data '{btn.data}' does not match regex"
    assert btn.data == "card_show:1"


def test_render_flashcard_revealed_state() -> None:
    card = Card()
    text, buttons = render_flashcard(
        card=card,
        question_text="What is repo rate?",
        answer_text="The rate at which RBI lends money to commercial banks.",
        is_revealed=True,
    )

    assert "What is repo rate?" in text
    assert "The rate at which RBI lends money to commercial banks." in text

    all_buttons = [b for row in buttons for b in row]
    assert len(all_buttons) == 4
    for b in all_buttons:
        assert CALLBACK_PATTERN.match(b.data), f"Button data '{b.data}' does not match regex"

    assert [b.text for b in all_buttons] == ["Again", "Hard", "Good", "Easy"]
    assert [b.data for b in all_buttons] == [
        "card_rate:1:1",
        "card_rate:1:2",
        "card_rate:1:3",
        "card_rate:1:4",
    ]


def test_render_flashcard_custom_card_id() -> None:
    card = Card()
    _, buttons = render_flashcard(
        card=card,
        question_text="Q",
        answer_text="A",
        is_revealed=True,
        card_id=42,
    )
    all_buttons = [b for row in buttons for b in row]
    assert [b.data for b in all_buttons] == [
        "card_rate:42:1",
        "card_rate:42:2",
        "card_rate:42:3",
        "card_rate:42:4",
    ]


def test_render_grammar_card() -> None:
    q = _sample_grammar_question()
    text, buttons = render_grammar_card(q, index=3, total=7)

    assert "Question 3/7:" in text
    assert q.sentence_with_blank in text
    assert f"A) {q.options[0]}" in text
    assert f"B) {q.options[1]}" in text
    assert f"C) {q.options[2]}" in text
    assert f"D) {q.options[3]}" in text

    all_buttons = [b for row in buttons for b in row]
    assert len(all_buttons) == 4
    for b in all_buttons:
        assert CALLBACK_PATTERN.match(b.data), f"Button data '{b.data}' does not match regex"

    assert [b.text for b in all_buttons] == ["A", "B", "C", "D"]
    assert [b.data for b in all_buttons] == [
        "gram_ans:1:0",
        "gram_ans:1:1",
        "gram_ans:1:2",
        "gram_ans:1:3",
    ]
