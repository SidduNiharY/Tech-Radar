from __future__ import annotations

from typing import Any

from techradar.english.writing import (
    Rubric,
    WritingFeedback,
    feedback_on_text,
    render_writing_feedback,
    route_and_validate_polish,
)
from tests.fakes import FakeCompleter


class FakeLT:
    async def check(self, text: str) -> list[Any]:
        return []


async def test_essay_feedback_has_rubric() -> None:
    expected_feedback = WritingFeedback(
        issues=[],
        improved="Dear Sir, I am writing to apply...",
        reasons=["More concise phrasing."],
        rubric=Rubric(structure=4, grammar=4, vocabulary=4, relevance=5),
    )
    completer = FakeCompleter([expected_feedback.model_dump_json()])
    fb = await feedback_on_text("Dear Sir, ...", "letter", FakeLT(), completer)
    assert fb.rubric is not None
    assert 1 <= fb.rubric.structure <= 5


def test_polish_too_long() -> None:
    assert route_and_validate_polish("x" * 2001) == "Keep it under 2,000 characters."
    assert route_and_validate_polish("short text") is None


def test_render_writing_feedback() -> None:
    fb = WritingFeedback(
        issues=[],
        improved="This is improved text.",
        reasons=["Clearer subject-verb agreement."],
        rubric=Rubric(structure=4, grammar=3, vocabulary=4, relevance=5),
    )
    rendered = render_writing_feedback(fb)
    assert "Improved:\nThis is improved text." in rendered
    assert "• Clearer subject-verb agreement." in rendered
    assert "Structure 4 · Grammar 3 · Vocabulary 4 · Relevance 5" in rendered
