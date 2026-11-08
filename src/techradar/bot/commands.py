"""Interactive command card rendering for Telegram bot (Phase 3).

SEC: SEC-20, SEC-26.
"""

from __future__ import annotations

import re
from typing import Any

from techradar.messaging.outbox import Button
from techradar.practice.fsrs import Card, Rating
from techradar.practice.grammar import GrammarQuestion
from techradar.practice.mcq import MCQDraft

__all__ = ["render_flashcard", "render_grammar_card", "render_quiz_card"]

_OPTION_LABELS = ("A", "B", "C", "D")


def _extract_id(obj: Any, default: int = 1) -> int:
    """Extract integer identifier from card or string ID for callback validation."""
    if isinstance(obj, int):
        return obj
    for attr in ("id", "card_id", "card_key", "key"):
        val = getattr(obj, attr, None)
        if val is not None:
            if isinstance(val, int):
                return val
            digits = re.sub(r"\D", "", str(val))
            if digits:
                return int(digits)
    if isinstance(obj, str):
        digits = re.sub(r"\D", "", obj)
        if digits:
            return int(digits)
    return default


def render_quiz_card(
    question: MCQDraft,
    question_index: int,
    total_questions: int,
) -> tuple[str, list[list[Button]]]:
    """Render an MCQ quiz question card with inline answer buttons."""
    lines = [
        f"Question {question_index}/{total_questions}:",
        "",
        question.question,
        "",
    ]
    for idx, opt in enumerate(question.options):
        label = _OPTION_LABELS[idx] if idx < len(_OPTION_LABELS) else str(idx + 1)
        lines.append(f"{label}) {opt}")

    text = "\n".join(lines)
    buttons = [
        [
            Button(text="A", data=f"quiz_ans:{question_index}:0"),
            Button(text="B", data=f"quiz_ans:{question_index}:1"),
            Button(text="C", data=f"quiz_ans:{question_index}:2"),
            Button(text="D", data=f"quiz_ans:{question_index}:3"),
        ]
    ]
    return (text, buttons)


def render_flashcard(
    card: Card,
    question_text: str,
    answer_text: str,
    is_revealed: bool = False,
    card_id: int | str | None = None,
) -> tuple[str, list[list[Button]]]:
    """Render a spaced repetition flashcard in initial or revealed state."""
    cid = _extract_id(card_id if card_id is not None else card)

    if not is_revealed:
        text = question_text
        buttons = [[Button(text="Show Answer", data=f"card_show:{cid}")]]
        return (text, buttons)

    text = f"{question_text}\n\nAnswer:\n{answer_text}"
    buttons = [
        [
            Button(text="Again", data=f"card_rate:{cid}:{int(Rating.AGAIN)}"),
            Button(text="Hard", data=f"card_rate:{cid}:{int(Rating.HARD)}"),
            Button(text="Good", data=f"card_rate:{cid}:{int(Rating.GOOD)}"),
            Button(text="Easy", data=f"card_rate:{cid}:{int(Rating.EASY)}"),
        ]
    ]
    return (text, buttons)


def render_grammar_card(
    q: GrammarQuestion,
    index: int,
    total: int,
) -> tuple[str, list[list[Button]]]:
    """Render a grammar question card with inline option buttons."""
    clean_id = _extract_id(q.id)
    lines = [
        f"Question {index}/{total}:",
        "",
        q.sentence_with_blank,
        "",
    ]
    for idx, opt in enumerate(q.options):
        label = _OPTION_LABELS[idx] if idx < len(_OPTION_LABELS) else str(idx + 1)
        lines.append(f"{label}) {opt}")

    text = "\n".join(lines)
    buttons = [
        [
            Button(text="A", data=f"gram_ans:{clean_id}:0"),
            Button(text="B", data=f"gram_ans:{clean_id}:1"),
            Button(text="C", data=f"gram_ans:{clean_id}:2"),
            Button(text="D", data=f"gram_ans:{clean_id}:3"),
        ]
    ]
    return (text, buttons)
