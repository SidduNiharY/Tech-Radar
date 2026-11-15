from __future__ import annotations

from techradar.night.window import (
    in_night_window,
    is_night_only,
    next_window_start,
    night_only,
)

NIGHT_JOB_NAMES: list[str] = [
    "summarize_chapters_job",
]


def night_jobs() -> list[str]:
    """Return names of Procrastinate tasks designated to run in the night window."""
    return list(NIGHT_JOB_NAMES)


__all__ = [
    "in_night_window",
    "is_night_only",
    "next_window_start",
    "night_jobs",
    "night_only",
]
