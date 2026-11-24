from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

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


def test_health_messages_are_exact():
    r = check_health(
        disk_free_pct=10.0,
        last_fetch_ok=NOW - timedelta(hours=7),
        enabled_sources=3,
        backup_status=None,
        ollama_ok=False,
        now=NOW,
    )
    assert dict(r.problems) == {
        "disk": "⚠️ Disk free is 10%.",
        "fetch": "⚠️ No news fetched for 7 hours.",
        "backup": "⚠️ Backup hasn't succeeded in 36 hours.",
        "ollama": "⚠️ Local models are down.",
    }


def test_read_backup_status(tmp_path):
    from techradar.ops.health import read_backup_status

    path = tmp_path / "backup.json"
    assert read_backup_status(path) is None  # missing
    path.write_text("not json")
    assert read_backup_status(path) is None
    path.write_text("[1]")
    assert read_backup_status(path) is None
    path.write_text('{"ok": true, "at": "2026-11-08T12:00:00+00:00"}')
    assert read_backup_status(path) == {"ok": True, "at": "2026-11-08T12:00:00+00:00"}


@pytest.mark.db
@pytest.mark.asyncio
async def test_run_health_checks_alerts_once_per_window(session):
    from sqlalchemy import update

    from techradar.db.models import Source
    from techradar.ops.health import run_health_checks

    kwargs = {
        "owner_chat_id": 4242,
        "disk_free_pct": 5.0,
        "ollama_ok": True,
        "backup_status": {"ok": True, "at": NOW.isoformat()},
    }
    # Other db tests leave committed sources behind; make every one fresh, so only the disk
    # check fires (rolled back with the session).
    await session.execute(update(Source).values(last_fetched_at=NOW))
    assert await run_health_checks(session, now=NOW, **kwargs) == ["disk"]
    assert await run_health_checks(session, now=NOW + timedelta(hours=1), **kwargs) == []
    assert await run_health_checks(session, now=NOW + timedelta(hours=7), **kwargs) == ["disk"]


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
