from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import Source
from techradar.ops.alerts import raise_alert


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


def read_backup_status(path: Path) -> dict[str, Any] | None:
    """`data/status/backup.json` (`{"ok": bool, "at": iso}`), or None when missing or broken."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError, ValueError:
        return None
    return data if isinstance(data, dict) else None


async def run_health_checks(
    session: AsyncSession,
    *,
    now: datetime,
    owner_chat_id: int,
    disk_free_pct: float,
    ollama_ok: bool,
    backup_status: dict[str, Any] | None,
) -> list[str]:
    """Hourly health check: gather the facts, alert once per problem key per 6 hours.

    The probes (disk, Ollama, the backup file) are passed in so the job decides how to reach
    them. Returns the keys that were sent. The caller commits.
    """
    enabled = int(
        (
            await session.execute(select(func.count(Source.id)).where(Source.enabled.is_(True)))
        ).scalar_one()
    )
    last_fetch = (
        await session.execute(
            select(func.max(Source.last_fetched_at)).where(Source.enabled.is_(True))
        )
    ).scalar_one()
    report = check_health(
        disk_free_pct=disk_free_pct,
        last_fetch_ok=last_fetch,
        enabled_sources=enabled,
        backup_status=backup_status,
        ollama_ok=ollama_ok,
        now=now,
    )
    sent: list[str] = []
    for key, text in report.problems:
        if await raise_alert(session, owner_chat_id, f"health:{key}", text, now):
            sent.append(key)
    return sent
