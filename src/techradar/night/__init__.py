from __future__ import annotations

from techradar.night.window import (
    in_night_window,
    is_night_only,
    next_window_start,
    night_only,
)


def night_jobs() -> list[str]:
    """Names of the jobs registered on the `night` queue (they must all be `night_only`)."""
    from techradar.worker.names import NIGHT_QUEUE
    from techradar.worker.tasks import app

    return sorted(name for name, task in app.tasks.items() if task.queue == NIGHT_QUEUE)


__all__ = [
    "in_night_window",
    "is_night_only",
    "next_window_start",
    "night_jobs",
    "night_only",
]
