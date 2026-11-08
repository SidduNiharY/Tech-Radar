from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import NamedTuple


class SourceRow(NamedTuple):
    id: int
    url: str
    interval_min: int
    last_fetched_at: datetime | None
    enabled: bool


def due_sources(sources: Sequence[SourceRow], now: datetime) -> list[SourceRow]:
    """Return sources that are enabled and due for fetching."""
    due: list[SourceRow] = []
    for s in sources:
        if not s.enabled:
            continue
        if s.last_fetched_at is None:
            due.append(s)
            continue
        cur = now
        last = s.last_fetched_at
        if cur.tzinfo is not None and last.tzinfo is None:
            last = last.replace(tzinfo=cur.tzinfo)
        elif cur.tzinfo is None and last.tzinfo is not None:
            cur = cur.replace(tzinfo=last.tzinfo)
        elapsed = (cur - last).total_seconds()
        if elapsed >= s.interval_min * 60:
            due.append(s)
    return due
