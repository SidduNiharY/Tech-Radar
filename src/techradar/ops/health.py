from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field


class HealthReport(BaseModel):
    """System health check problems report."""

    problems: list[tuple[str, str]] = Field(default_factory=list)


def check_health(
    *,
    disk_free_pct: float,
    last_fetch_ok: datetime | None,
    enabled_sources: int,
    backup_status: dict[str, Any] | None,
    ollama_ok: bool,
    now: datetime,
) -> HealthReport:
    """Evaluate core system invariants and return list of (key, text) problems.

    Rules:
    - Disk below 15%: ⚠️ Disk free is <n>%.
    - Last successful fetch > 6h ago while sources enabled: ⚠️ No news fetched for <h> hours.
    - Backup status missing, older than 36h, or not ok: ⚠️ Backup hasn't succeeded in 36 hours.
    - Ollama down: ⚠️ Local models are down.
    """
    problems: list[tuple[str, str]] = []

    if disk_free_pct < 15.0:
        problems.append(("disk", f"⚠️ Disk free is {disk_free_pct:.0f}%."))

    if enabled_sources > 0:
        if last_fetch_ok is None:
            problems.append(("fetch", "⚠️ No news fetched yet."))
        else:
            diff = now - last_fetch_ok
            if diff > timedelta(hours=6):
                hours = int(diff.total_seconds() // 3600)
                problems.append(("fetch", f"⚠️ No news fetched for {hours} hours."))

    if backup_status is None or not backup_status.get("ok"):
        problems.append(("backup", "⚠️ Backup hasn't succeeded in 36 hours."))
    else:
        at_val = backup_status.get("at")
        if at_val:
            try:
                at_dt = datetime.fromisoformat(at_val)
                if at_dt.tzinfo is None:
                    at_dt = at_dt.replace(tzinfo=UTC)
                if (now - at_dt) > timedelta(hours=36):
                    problems.append(("backup", "⚠️ Backup hasn't succeeded in 36 hours."))
            except ValueError:
                problems.append(("backup", "⚠️ Backup hasn't succeeded in 36 hours."))
        else:
            problems.append(("backup", "⚠️ Backup hasn't succeeded in 36 hours."))

    if not ollama_ok:
        problems.append(("ollama", "⚠️ Local models are down."))

    return HealthReport(problems=problems)
