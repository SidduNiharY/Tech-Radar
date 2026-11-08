from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any


class MistakeDict(dict[str, Any]):
    """Dictionary supporting both item and attribute access for mistake fields."""

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError:
            raise AttributeError(f"'MistakeDict' object has no attribute '{name}'") from None

    def __setattr__(self, name: str, value: Any) -> None:
        self[name] = value


class MistakesNotebook:
    """Notebook for tracking incorrect quiz answers and scheduling targeted reviews."""

    def __init__(self) -> None:
        self._mistakes_by_id: dict[str, MistakeDict] = {}
        self._user_mistakes: dict[int, list[str]] = defaultdict(list)

    def record_quiz_mistake(
        self,
        user_id: int,
        question_id: str,
        question_text: str,
        chosen_option: str,
        correct_option: str,
        explanation: str,
    ) -> str:
        """Records a mistake from a quiz attempt with a unique ID."""
        mistake_id = f"mstk_{uuid.uuid4().hex[:16]}"
        entry = MistakeDict(
            id=mistake_id,
            user_id=user_id,
            question_id=question_id,
            question_text=question_text,
            chosen_option=str(chosen_option),
            correct_option=str(correct_option),
            explanation=explanation,
            resolved=False,
            created_at=datetime.now(UTC),
            resolved_at=None,
        )
        self._mistakes_by_id[mistake_id] = entry
        self._user_mistakes[user_id].append(mistake_id)
        return mistake_id

    def get_active_mistakes(self, user_id: int) -> list[dict[str, Any]]:
        """Returns unresolved mistake entries for priority review."""
        mistake_ids = self._user_mistakes.get(user_id, [])
        active: list[dict[str, Any]] = []
        for mid in mistake_ids:
            entry = self._mistakes_by_id.get(mid)
            if entry and not entry["resolved"]:
                active.append(dict(entry))
        return active

    def resolve_mistake(self, mistake_id: str) -> None:
        """Marks a mistake as resolved after successful re-testing."""
        entry = self._mistakes_by_id.get(mistake_id)
        if entry is not None:
            entry["resolved"] = True
            entry["resolved_at"] = datetime.now(UTC)

    # Backwards compatibility with quiz.py interface
    def record_mistake(
        self,
        user_id: int,
        question_id: str,
        chosen_option: int | str,
        correct_option: int | str,
        explanation: str,
    ) -> str:
        return self.record_quiz_mistake(
            user_id=user_id,
            question_id=question_id,
            question_text="",
            chosen_option=str(chosen_option),
            correct_option=str(correct_option),
            explanation=explanation,
        )

    def get_mistakes(self, user_id: int) -> list[dict[str, Any]]:
        return self.get_active_mistakes(user_id)
