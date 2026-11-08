from __future__ import annotations

from datetime import UTC, datetime, timedelta

from techradar.ops.health import check_health

NOW = datetime(2026, 11, 8, 12, 0, 0, tzinfo=UTC)


def test_health_rules_all_failing():
    r = check_health(
        disk_free_pct=10.0,
        last_fetch_ok=NOW - timedelta(hours=7),
        enabled_sources=3,
        backup_status={"ok": True, "at": (NOW - timedelta(hours=40)).isoformat()},
        ollama_ok=False,
        now=NOW,
    )
    assert {k for k, _ in r.problems} == {"disk", "fetch", "backup", "ollama"}


def test_health_rules_all_passing():
    r = check_health(
        disk_free_pct=45.0,
        last_fetch_ok=NOW - timedelta(hours=1),
        enabled_sources=5,
        backup_status={"ok": True, "at": (NOW - timedelta(hours=12)).isoformat()},
        ollama_ok=True,
        now=NOW,
    )
    assert len(r.problems) == 0


def test_health_disk_threshold():
    r = check_health(
        disk_free_pct=14.9,
        last_fetch_ok=NOW,
        enabled_sources=1,
        backup_status={"ok": True, "at": NOW.isoformat()},
        ollama_ok=True,
        now=NOW,
    )
    assert len(r.problems) == 1
    assert r.problems[0][0] == "disk"
    assert "⚠️ Disk free is 15%" in r.problems[0][1] or "14%" in r.problems[0][1]


def test_health_backup_missing_or_not_ok():
    # Missing backup status
    r1 = check_health(
        disk_free_pct=50.0,
        last_fetch_ok=NOW,
        enabled_sources=0,
        backup_status=None,
        ollama_ok=True,
        now=NOW,
    )
    assert any(k == "backup" for k, _ in r1.problems)

    # Backup marked not ok
    r2 = check_health(
        disk_free_pct=50.0,
        last_fetch_ok=NOW,
        enabled_sources=0,
        backup_status={"ok": False, "at": NOW.isoformat()},
        ollama_ok=True,
        now=NOW,
    )
    assert any(k == "backup" for k, _ in r2.problems)


def test_health_fetch_ignored_if_no_sources_enabled():
    r = check_health(
        disk_free_pct=50.0,
        last_fetch_ok=None,
        enabled_sources=0,
        backup_status={"ok": True, "at": NOW.isoformat()},
        ollama_ok=True,
        now=NOW,
    )
    assert not any(k == "fetch" for k, _ in r.problems)
