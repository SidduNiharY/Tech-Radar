"""Tests for Alert model, rendering, quiet hours, heartbeat, and alert logging."""

from datetime import UTC, datetime, time, timedelta
from pathlib import Path

import pytest

from techradar.hostsec.alerts import (
    Alert,
    AlertLog,
    Level,
    feed_alerter,
    group_key,
    parse_quiet_hours,
    render_alert,
    render_heartbeat,
    should_send_now,
)

NOW = datetime(2026, 11, 8, 10, 0, tzinfo=UTC)


def critical(
    service: str | None = None,
    rule: str = "critical rule",
    summary: str = "critical summary",
    at: datetime | None = None,
) -> Alert:
    return Alert(
        level=Level.CRITICAL,
        source="alerter",
        rule=rule,
        service=service,
        summary=summary,
        at=at or NOW,
    )


def warning(
    rule: str = "warning rule",
    summary: str = "warning summary",
    service: str | None = None,
    at: datetime | None = None,
) -> Alert:
    return Alert(
        level=Level.WARNING,
        source="alerter",
        rule=rule,
        service=service,
        summary=summary,
        at=at or NOW,
    )


def alert(
    summary: str,
    level: Level = Level.CRITICAL,
    service: str | None = None,
    rule: str = "test",
) -> Alert:
    return Alert(
        level=level,
        source="alerter",
        rule=rule,
        service=service,
        summary=summary,
        at=NOW,
    )


def at_local(time_str: str) -> datetime:
    h, m = [int(x) for x in time_str.split(":")]
    return datetime(2026, 11, 8, h, m, tzinfo=UTC)


def test_render_alert_redacts_tokens() -> None:
    a = alert(summary="token 1234567890:AAEhBP0av28AAAAAAAAAAAAAAAAAAAAAAAA seen")
    rendered = render_alert(a, "alert only")
    assert "AAEhBP0av28" not in rendered
    assert "[REDACTED]" in rendered
    assert "🚨 CRITICAL · host · test" in rendered
    assert "alert only" in rendered


def test_render_alert_service_and_level() -> None:
    a = warning("disk full", "disk at 98%", service="parser")
    rendered = render_alert(a, "contained")
    assert "⚠️ WARNING · parser · disk full" in rendered
    assert "contained" in rendered


def test_group_key() -> None:
    a = critical(service="parser", rule="shell")
    assert group_key(a) == "alerter:shell:parser"


def test_warnings_grouped_per_hour() -> None:
    msgs = feed_alerter(
        [warning("squid deny", at=NOW + timedelta(minutes=10 * i)) for i in range(5)]
    )
    assert len(msgs) == 1 and msgs[0].endswith("(×5)")


def test_warnings_different_keys_not_grouped() -> None:
    msgs = feed_alerter([
        warning("rule-1", at=NOW),
        warning("rule-2", at=NOW + timedelta(minutes=5)),
    ])
    assert len(msgs) == 2


def test_quiet_hours_hold_warnings_not_criticals() -> None:
    q = (time(23), time(6))
    assert should_send_now(critical(), at_local("02:00"), q) and not should_send_now(
        warning(), at_local("02:00"), q
    )
    # Outside quiet hours
    assert should_send_now(warning(), at_local("12:00"), q)
    # Info is never sent now
    info_alert = Alert(
        level=Level.INFO,
        source="alerter",
        rule="test",
        summary="info",
        at=NOW,
    )
    assert not should_send_now(info_alert, at_local("12:00"), q)


def test_parse_quiet_hours() -> None:
    start, end = parse_quiet_hours("23:00-06:00")
    assert (start, end) == (time(23, 0), time(6, 0))


def test_parse_quiet_hours_invalid() -> None:
    with pytest.raises(ValueError, match="Invalid quiet hours"):
        parse_quiet_hours("invalid")


def test_heartbeat_texts() -> None:
    assert (
        render_heartbeat([])
        == "✅ All quiet: 0 critical, 0 warnings in the last 24 h."
    )
    assert render_heartbeat([critical()]).startswith("⚠️ 1 critical, 0 warnings")
    assert "Check the Security screen or the alert log." in render_heartbeat([critical()])


def test_alert_log_is_append_only(tmp_path: Path) -> None:
    log = AlertLog(tmp_path / "a.jsonl")
    log.append(critical())
    first = (tmp_path / "a.jsonl").read_text(encoding="utf-8")
    log.append(warning("x"))
    assert (tmp_path / "a.jsonl").read_text(encoding="utf-8").startswith(first)


def test_alert_log_since(tmp_path: Path) -> None:
    log = AlertLog(tmp_path / "a.jsonl")
    t1 = NOW - timedelta(hours=2)
    t2 = NOW - timedelta(hours=1)
    t3 = NOW

    log.append(critical(at=t1))
    log.append(warning(at=t2))
    log.append(critical(at=t3))

    results = log.since(NOW - timedelta(minutes=90))
    assert len(results) == 2
    assert results[0].at == t2
    assert results[1].at == t3


def test_alert_log_rotation(tmp_path: Path) -> None:
    # Small max_bytes to force rotation
    log_file = tmp_path / "a.jsonl"
    log = AlertLog(log_file, max_bytes=200, backup_count=3)

    for i in range(5):
        log.append(critical(rule=f"rule-{i}"))

    # Must have rotated files
    assert log_file.exists()
    assert (tmp_path / "a.jsonl.1").exists()
    # Reading since includes rotated files
    results = log.since(NOW - timedelta(days=1))
    assert len(results) == 5
