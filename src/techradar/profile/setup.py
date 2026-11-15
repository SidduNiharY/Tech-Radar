"""Interactive profile setup choices and button generation."""

from __future__ import annotations

from typing import Any

from techradar.feedback.patterns import Mode
from techradar.feedback.rules import StyleField, StyleRule
from techradar.messaging.outbox import Button

SETUP_QUESTIONS: list[dict[str, Any]] = [
    {
        "field": "length",
        "question": "How long should typical answers be?",
        "options": [
            ("short", "Short (<120w)"),
            ("medium", "Medium (~250w)"),
            ("long", "Comprehensive"),
        ],
    },
    {
        "field": "order",
        "question": "How should concepts be introduced?",
        "options": [
            ("formula_first", "Formula first"),
            ("example_first", "Example first"),
            ("definition_first", "Definition first"),
        ],
    },
    {
        "field": "examples",
        "question": "How many examples do you prefer?",
        "options": [
            ("none", "None"),
            ("one", "One example"),
            ("two", "Two examples"),
        ],
    },
]


def get_setup_questions(mode: Mode) -> list[dict[str, Any]]:
    """Return setup questions for a mode."""
    return SETUP_QUESTIONS


def setup_buttons(mode: Mode, question_index: int) -> list[list[Button]]:
    """Build inline buttons for a setup question step with integer callback arguments."""
    if question_index < 0 or question_index >= len(SETUP_QUESTIONS):
        return []

    q = SETUP_QUESTIONS[question_index]
    options: list[tuple[str, str]] = q["options"]
    row: list[Button] = [
        Button(
            text=label,
            data=f"set_{mode.value}:{question_index}:{opt_idx}",
        )
        for opt_idx, (_, label) in enumerate(options)
    ]
    return [row]


def parse_setup_choice(
    mode: Mode,
    question_index: int,
    choice: int | str,
) -> StyleRule:
    """Convert setup answer selection into an active StyleRule."""
    if question_index < 0 or question_index >= len(SETUP_QUESTIONS):
        raise ValueError(f"Invalid question index {question_index}")

    q = SETUP_QUESTIONS[question_index]
    options: list[tuple[str, str]] = q["options"]

    if isinstance(choice, int) or (isinstance(choice, str) and choice.isdigit()):
        idx = int(choice)
        if 0 <= idx < len(options):
            val = options[idx][0]
        else:
            raise ValueError(f"Invalid choice index {choice}")
    else:
        val = str(choice)

    field_name: StyleField = q["field"]
    return StyleRule(
        mode=mode,
        field=field_name,
        value=val,
    )
