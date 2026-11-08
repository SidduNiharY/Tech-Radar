from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


class _RecordTakeDescriptor:
    """Hybrid descriptor allowing record_take to be called on class or instance."""

    def __get__(self, instance: Any, owner: Any = None) -> Any:
        def _wrapper(
            briefing_id: str,
            message_id: int,
            user_text: str,
            valid_briefing_message_ids: set[int],
        ) -> dict[str, Any]:
            store = (
                instance._takes if instance is not None and hasattr(instance, "_takes") else None
            )
            return PredictionTracker._record_take_impl(
                briefing_id=briefing_id,
                message_id=message_id,
                user_text=user_text,
                valid_briefing_message_ids=valid_briefing_message_ids,
                store=store,
            )

        return _wrapper


class PredictionTracker:
    """Tracks user opinions and predictions in response to daily briefing messages."""

    MAX_TEXT_LENGTH = 500

    def __init__(self) -> None:
        self._takes: list[dict[str, Any]] = []

    record_take = _RecordTakeDescriptor()

    @staticmethod
    def _record_take_impl(
        briefing_id: str,
        message_id: int,
        user_text: str,
        valid_briefing_message_ids: set[int],
        store: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        if message_id not in valid_briefing_message_ids:
            raise ValueError("Reply must be to an active briefing message")
        if len(user_text) > PredictionTracker.MAX_TEXT_LENGTH:
            raise ValueError(
                f"User text exceeds maximum length of "
                f"{PredictionTracker.MAX_TEXT_LENGTH} characters"
            )

        take = {
            "briefing_id": briefing_id,
            "message_id": message_id,
            "text": user_text,
            "created_at": datetime.now(UTC),
        }
        if store is not None:
            store.append(take)
        return take

    def get_takes(self) -> list[dict[str, Any]]:
        """Returns all recorded takes."""
        return list(self._takes)
