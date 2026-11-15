from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from techradar.llm.client import Role, complete_json
from techradar.practice.mcq import MCQDraft


class CheckerAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answer_index: int


async def reading_quiz(note_text: str, completer: Any, max_questions: int = 5) -> list[MCQDraft]:
    """Generate reading comprehension MCQs where correct options appear verbatim in source text."""
    normalized_note = " ".join(note_text.split())
    valid_drafts: list[MCQDraft] = []

    for _ in range(max_questions):
        try:
            draft = await complete_json(
                completer,
                Role.WORKER,
                "You write a reading comprehension question based on the note text. "
                "The correct option must appear word-for-word in the text.",
                note_text,
                MCQDraft,
            )
        except IndexError, Exception:
            break

        # Check verbatim in note text
        correct_text = " ".join(draft.options[draft.answer_index].split())
        if correct_text not in normalized_note:
            continue

        # Check checker agreement
        try:
            check_ans = await complete_json(
                completer,
                Role.CHECKER,
                "Answer the multiple choice question based on the text.",
                f"Text:\n{note_text}\n\nQuestion:\n{draft.question}\nOptions:\n{draft.options}",
                CheckerAnswer,
            )
        except IndexError, Exception:
            break

        if check_ans.answer_index != draft.answer_index:
            continue

        valid_drafts.append(draft)

    return valid_drafts
