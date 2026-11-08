from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


class QueuedTask(BaseModel):
    """Represents a scheduled asynchronous task that may require catchup after downtime."""

    id: str
    task_type: str
    scheduled_at: datetime
    priority: int = 1
    payload: dict[str, Any] = Field(default_factory=dict)


class CatchupEngine:
    """Engine to detect overdue tasks after system offline downtime."""

    @staticmethod
    def detect_missed_tasks(
        queued_tasks: list[QueuedTask],
        current_time: datetime,
        max_catchup_limit: int = 5,
    ) -> list[QueuedTask]:
        """Identifies overdue tasks from offline downtime.

        Sorts by priority descending and scheduled_at ascending, and strictly
        caps the catchup batch at max_catchup_limit to prevent thundering herd.
        """
        if max_catchup_limit <= 0 or not queued_tasks:
            return []

        def _to_utc_timestamp(dt: datetime) -> float:
            if dt.tzinfo is None:
                return dt.replace(tzinfo=UTC).timestamp()
            return dt.timestamp()

        current_ts = _to_utc_timestamp(current_time)

        # Identify overdue tasks (scheduled_at <= current_time)
        overdue: list[QueuedTask] = [
            task for task in queued_tasks if _to_utc_timestamp(task.scheduled_at) <= current_ts
        ]

        # Sort: priority descending (-priority), scheduled_at ascending (ts)
        overdue.sort(key=lambda t: (-t.priority, _to_utc_timestamp(t.scheduled_at)))

        return overdue[:max_catchup_limit]
