import pytest
from pydantic import ValidationError

from techradar.practice.mcq import MCQDraft, MCQOption, shuffle_options


def test_mcq_option_valid():
    opt = MCQOption(text="New Delhi", option_id="opt_1")
    assert opt.text == "New Delhi"
    assert opt.option_id == "opt_1"


def test_mcq_draft_valid():
    draft = MCQDraft(
        question="What is the capital of India?",
        options=["Mumbai", "New Delhi", "Kolkata", "Chennai"],
        answer_index=1,
        explanation="New Delhi is the official capital of India.",
    )
    assert draft.question == "What is the capital of India?"
    assert len(draft.options) == 4
    assert draft.answer_index == 1
    assert draft.explanation == "New Delhi is the official capital of India."


def test_mcq_draft_rejects_fewer_than_four_options():
    with pytest.raises(ValidationError, match="4"):
        MCQDraft(
            question="What is the capital of India?",
            options=["Mumbai", "New Delhi", "Kolkata"],
            answer_index=1,
            explanation="Explanation text here.",
        )


def test_mcq_draft_rejects_more_than_four_options():
    with pytest.raises(ValidationError, match="4"):
        MCQDraft(
            question="What is the capital of India?",
            options=["Mumbai", "New Delhi", "Kolkata", "Chennai", "Bengaluru"],
            answer_index=1,
            explanation="Explanation text here.",
        )


def test_mcq_draft_rejects_non_unique_options():
    with pytest.raises(ValidationError, match="unique"):
        MCQDraft(
            question="What is the capital of India?",
            options=["New Delhi", "New Delhi", "Kolkata", "Chennai"],
            answer_index=0,
            explanation="Explanation text here.",
        )


def test_mcq_draft_rejects_invalid_answer_index():
    with pytest.raises(ValidationError):
        MCQDraft(
            question="What is the capital of India?",
            options=["Mumbai", "New Delhi", "Kolkata", "Chennai"],
            answer_index=-1,
            explanation="Explanation text here.",
        )

    with pytest.raises(ValidationError):
        MCQDraft(
            question="What is the capital of India?",
            options=["Mumbai", "New Delhi", "Kolkata", "Chennai"],
            answer_index=4,
            explanation="Explanation text here.",
        )


def test_mcq_draft_rejects_question_length_boundaries():
    # Less than 10 chars
    with pytest.raises(ValidationError):
        MCQDraft(
            question="Short?",
            options=["A", "B", "C", "D"],
            answer_index=0,
            explanation="Explanation text here.",
        )

    # Greater than 300 chars
    with pytest.raises(ValidationError):
        MCQDraft(
            question="Q" * 301,
            options=["A", "B", "C", "D"],
            answer_index=0,
            explanation="Explanation text here.",
        )


def test_mcq_draft_rejects_links():
    # Link in question
    with pytest.raises(ValidationError, match="links are not allowed"):
        MCQDraft(
            question="Visit https://example.com for the question?",
            options=["A", "B", "C", "D"],
            answer_index=0,
            explanation="Valid explanation.",
        )

    # Link in options
    with pytest.raises(ValidationError, match="links are not allowed"):
        MCQDraft(
            question="What is the official URL?",
            options=["https://example.com", "Option B", "Option C", "Option D"],
            answer_index=0,
            explanation="Valid explanation.",
        )

    # Link in explanation
    with pytest.raises(ValidationError, match="links are not allowed"):
        MCQDraft(
            question="What is the capital of India?",
            options=["Mumbai", "New Delhi", "Kolkata", "Chennai"],
            answer_index=1,
            explanation="Check out http://rbi.org.in for info.",
        )


def test_shuffle_options_deterministic_and_tracks_key():
    draft = MCQDraft(
        question="What is the capital of India?",
        options=["Mumbai", "New Delhi", "Kolkata", "Chennai"],
        answer_index=1,
        explanation="New Delhi is the official capital.",
    )
    correct_option_text = draft.options[draft.answer_index]

    shuffled_1 = shuffle_options(draft, seed=42)
    shuffled_2 = shuffle_options(draft, seed=42)

    assert shuffled_1 == shuffled_2
    assert shuffled_1.options[shuffled_1.answer_index] == correct_option_text
    assert set(shuffled_1.options) == set(draft.options)
