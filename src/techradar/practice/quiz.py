from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from techradar.practice.fsrs import Card, State
from techradar.practice.mcq import MCQDraft


class TwoModelKeyChecker:
    """Checks generated MCQ keys against a secondary model's answer pick (SEC-20)."""

    @staticmethod
    def verify_mcq_key(draft: MCQDraft, checker_answer_index: int) -> bool:
        """Compares generator's draft.answer_index with secondary model's checker_answer_index.

        If they disagree, returns False (MCQ dropped and never shown, SEC-20).
        """
        return draft.answer_index == checker_answer_index


class _FilterCallable:
    def __init__(self, target: Any) -> None:
        self.target = target

    def __call__(
        self,
        due_cards: list[Card],
        is_final_mode: bool = False,
    ) -> list[Card]:
        new_limit = getattr(self.target, "new_limit", getattr(self.target, "DEFAULT_NEW_LIMIT", 10))
        review_limit = getattr(
            self.target,
            "review_limit",
            getattr(self.target, "DEFAULT_REVIEW_LIMIT", 40),
        )
        final_limit = getattr(
            self.target,
            "final_mode_review_limit",
            getattr(self.target, "DEFAULT_FINAL_MODE_REVIEW_LIMIT", 80),
        )
        max_reviews = final_limit if is_final_mode else review_limit
        new_cards = [c for c in due_cards if c.state == State.NEW]
        review_cards = [c for c in due_cards if c.state != State.NEW]
        return new_cards[:new_limit] + review_cards[:max_reviews]


class _HybridFilterDescriptor:
    def __get__(self, instance: Any, owner: Any = None) -> _FilterCallable:
        if instance is not None:
            return _FilterCallable(instance)
        return _FilterCallable(owner)


class DailyPracticeLimits:
    """Daily study limits: 10 new cards, 40 reviews (80 in final 30 days exam mode)."""

    DEFAULT_NEW_LIMIT = 10
    DEFAULT_REVIEW_LIMIT = 40
    DEFAULT_FINAL_MODE_REVIEW_LIMIT = 80

    def __init__(
        self,
        new_limit: int = DEFAULT_NEW_LIMIT,
        review_limit: int = DEFAULT_REVIEW_LIMIT,
        final_mode_review_limit: int = DEFAULT_FINAL_MODE_REVIEW_LIMIT,
    ) -> None:
        self.new_limit = new_limit
        self.review_limit = review_limit
        self.final_mode_review_limit = final_mode_review_limit

    filter_due_cards = _HybridFilterDescriptor()


class MistakeEntry(BaseModel):
    user_id: int
    question_id: str
    chosen_option: int
    correct_option: int
    explanation: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def __getitem__(self, item: str) -> Any:
        return getattr(self, item)


class MistakesNotebook:
    """Records incorrect quiz answers for prioritized spaced repetition."""

    def __init__(self) -> None:
        self._mistakes: dict[int, list[MistakeEntry]] = defaultdict(list)

    def record_mistake(
        self,
        user_id: int,
        question_id: str,
        chosen_option: int,
        correct_option: int,
        explanation: str,
    ) -> None:
        entry = MistakeEntry(
            user_id=user_id,
            question_id=question_id,
            chosen_option=chosen_option,
            correct_option=correct_option,
            explanation=explanation,
        )
        self._mistakes[user_id].append(entry)

    def get_mistakes(self, user_id: int) -> list[MistakeEntry]:
        return list(self._mistakes.get(user_id, []))

    def get_user_mistakes(self, user_id: int) -> list[MistakeEntry]:
        return self.get_mistakes(user_id)

    def __getitem__(self, user_id: int) -> list[MistakeEntry]:
        return self.get_mistakes(user_id)

    @property
    def mistakes(self) -> dict[int, list[MistakeEntry]]:
        return self._mistakes
