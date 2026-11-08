"""Host security alert definitions, log management, and heartbeat rendering."""

import logging
import os
from collections.abc import Sequence
from datetime import UTC, datetime, time, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from techradar.logs import RedactingFilter

logger = logging.getLogger(__name__)


class Level(StrEnum):
    """Alert severity levels."""

    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class Alert(BaseModel):
    """Structured security alert."""

    level: Level
    source: Literal[
        "falco",
        "auditd",
        "journal",
        "pgaudit",
        "squid",
        "aide",
        "integrity",
        "resources",
        "gateway",
        "alerter",
    ]
    rule: str = Field(max_length=80)
    service: str | None = Field(default=None, pattern=r"^[a-z0-9-]{1,40}$")
    summary: str = Field(max_length=200)
    at: datetime


def render_alert(a: Alert, action: str) -> str:
    """Format alert message with token redaction for notifications."""
    if a.level == Level.CRITICAL:
        prefix = "🚨 CRITICAL"
    elif a.level == Level.WARNING:
        prefix = "⚠️ WARNING"
    else:
        prefix = "ℹ️ INFO"

    target = a.service or "host"
    redacted_summary = RedactingFilter().redact(a.summary)
    time_str = a.at.strftime("%H:%M")
    return f"{prefix} · {target} · {a.rule}\n{redacted_summary}\n{time_str} · {action}"


def group_key(a: Alert) -> str:
    """Compute deduplication and grouping key for an alert."""
    return f"{a.source}:{a.rule}:{a.service}"


def parse_quiet_hours(raw: str) -> tuple[time, time]:
    """Parse a quiet hours range string like '23:00-06:00'."""
    parts = raw.strip().split("-")
    if len(parts) != 2:
        msg = f"Invalid quiet hours format: {raw}"
        raise ValueError(msg)
    start_parts = [int(p) for p in parts[0].split(":")]
    end_parts = [int(p) for p in parts[1].split(":")]
    return time(start_parts[0], start_parts[1]), time(end_parts[0], end_parts[1])


def should_send_now(a: Alert, now_local: datetime, quiet: tuple[time, time]) -> bool:
    """Determine whether alert should be sent immediately or held."""
    if a.level == Level.CRITICAL:
        return True
    if a.level == Level.INFO:
        return False

    # Warning logic: send outside quiet hours, hold within quiet hours
    start, end = quiet
    t = now_local.time()
    if start <= end:
        in_quiet = start <= t < end
    else:
        in_quiet = t >= start or t < end
    return not in_quiet


class AlertLog:
    """Append-only alert log with automatic size rotation."""

    def __init__(
        self,
        path: Path,
        max_bytes: int = 10 * 1024 * 1024,
        backup_count: int = 12,
    ) -> None:
        self.path = Path(path)
        self.max_bytes = max_bytes
        self.backup_count = backup_count

    def _rotate_if_needed(self) -> None:
        if not self.path.exists() or self.path.stat().st_size < self.max_bytes:
            return

        for i in range(self.backup_count, 0, -1):
            src = (
                self.path.with_name(f"{self.path.name}.{i - 1}")
                if i > 1
                else self.path
            )
            dst = self.path.with_name(f"{self.path.name}.{i}")
            if src.exists():
                if i == self.backup_count and dst.exists():
                    dst.unlink(missing_ok=True)
                src.rename(dst)

    def append(self, a: Alert) -> None:
        """Append an alert as a JSON line with mode 0o640 and size rotation."""
        self._rotate_if_needed()
        self.path.parent.mkdir(parents=True, exist_ok=True)

        payload = (a.model_dump_json() + "\n").encode("utf-8")
        fd = os.open(
            self.path,
            os.O_WRONLY | os.O_CREAT | os.O_APPEND,
            0o640,
        )
        try:
            os.write(fd, payload)
        finally:
            os.close(fd)
        try:
            os.chmod(self.path, 0o640)
        except OSError:
            pass

    def since(self, t: datetime) -> list[Alert]:
        """Read all alerts logged at or after timestamp t."""
        alerts: list[Alert] = []
        files_to_check: list[Path] = []

        for i in range(self.backup_count, 0, -1):
            rotated = self.path.with_name(f"{self.path.name}.{i}")
            if rotated.exists():
                files_to_check.append(rotated)
        if self.path.exists():
            files_to_check.append(self.path)

        t_aware = t if t.tzinfo is not None else t.replace(tzinfo=UTC)

        for filepath in files_to_check:
            try:
                lines = filepath.read_text(encoding="utf-8").splitlines()
            except OSError:
                continue

            for line in lines:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    alert = Alert.model_validate_json(stripped)
                except (ValidationError, ValueError) as exc:
                    logger.debug("Skipping invalid alert log line: %s", exc)
                    continue

                alert_aware = (
                    alert.at
                    if alert.at.tzinfo is not None
                    else alert.at.replace(tzinfo=UTC)
                )
                if alert_aware >= t_aware:
                    alerts.append(alert)

        alerts.sort(key=lambda item: item.at)
        return alerts


def render_heartbeat(alerts_24h: Sequence[Alert]) -> str:
    """Render daily heartbeat summary string."""
    critical = sum(1 for a in alerts_24h if a.level == Level.CRITICAL)
    warnings = sum(1 for a in alerts_24h if a.level == Level.WARNING)

    if critical == 0:
        return f"✅ All quiet: 0 critical, {warnings} warnings in the last 24 h."
    return (
        f"⚠️ {critical} critical, {warnings} warnings in the last 24 h. "
        "Check the Security screen or the alert log."
    )


def feed_alerter(
    alerts: Sequence[Alert],
    action: str = "alert only",
) -> list[str]:
    """Group warnings with same key within 60 min into single messages ending in (×n)."""
    messages: list[str] = []
    window = timedelta(minutes=60)

    # Process sequentially preserving alert arrival order
    warning_clusters: dict[str, list[Alert]] = {}

    for a in alerts:
        if a.level == Level.CRITICAL:
            messages.append(render_alert(a, action))
            continue

        if a.level == Level.INFO:
            continue

        key = group_key(a)
        cluster = warning_clusters.get(key)
        if not cluster:
            warning_clusters[key] = [a]
        else:
            first = cluster[0]
            if a.at - first.at <= window:
                cluster.append(a)
            else:
                # Flush existing cluster
                count = len(cluster)
                msg = render_alert(cluster[0], action)
                if count > 1:
                    msg = f"{msg} (×{count})"
                messages.append(msg)
                warning_clusters[key] = [a]

    # Flush remaining warning clusters
    for cluster in warning_clusters.values():
        count = len(cluster)
        msg = render_alert(cluster[0], action)
        if count > 1:
            msg = f"{msg} (×{count})"
        messages.append(msg)

    return messages
