"""Learner topic mastery level computation and prompt guidance."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Literal

Level = Literal["new", "learning", "exam_ready", "mastered"]


def mastery_level(
    quiz_accuracy: float | None,
    stability_days: float | None,
    reviews: int,
) -> Level:
    """Compute mastery tier based on quiz performance and FSRS card stability."""
    if quiz_accuracy is None and reviews < 3:
        return "new"

    if (
        quiz_accuracy is not None
        and quiz_accuracy >= 0.90
        and stability_days is not None
        and stability_days >= 60.0
    ):
        return "mastered"

    if (
        quiz_accuracy is not None
        and quiz_accuracy >= 0.80
        and stability_days is not None
        and stability_days >= 21.0
    ):
        return "exam_ready"

    return "learning"


def mastery_line(
    levels: Mapping[str, Level],
    topics_in_question: Sequence[str],
) -> str | None:
    """Generate prompt skip-basics guidance line for mastered topics."""
    mastered = [t for t in topics_in_question if levels.get(t) == "mastered"]
    if not mastered:
        return None
    joined = ", ".join(mastered)
    return f"I already know these well, so skip their basics: {joined}."
