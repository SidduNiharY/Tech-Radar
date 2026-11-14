import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def test_backup_timer_is_persistent() -> None:
    timer = (REPO_ROOT / "infra/backup/techradar-backup.timer").read_text()
    assert "OnCalendar=*-*-* 02:30:00" in timer and "Persistent=true" in timer
    assert "WantedBy=timers.target" in timer


def test_backup_service_unit() -> None:
    service = (REPO_ROOT / "infra/backup/techradar-backup.service").read_text()
    assert "Type=oneshot" in service
    assert "backup.sh" in service


def test_backup_scripts_have_strict_mode() -> None:
    scripts = [
        REPO_ROOT / "infra/backup/backup.sh",
        REPO_ROOT / "infra/backup/restore_test.sh",
    ]
    for script in scripts:
        assert script.exists(), f"Script {script} does not exist"
        content = script.read_text()
        assert content.startswith("#!/bin/bash"), f"{script.name} must start with #!/bin/bash"
        assert "set -euo pipefail" in content, f"{script.name} must contain 'set -euo pipefail'"

        res = subprocess.run(  # noqa: S603
            ["bash", "-n", str(script)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert res.returncode == 0, f"bash -n failed on {script.name}: {res.stderr}"


def test_host_backup_scripts_default_to_the_repo_data_folder():
    # Both scripts run on the host from the repo (the backup unit sets
    # BACKUP_DIR=<repo>/data/backup). make gate-1 runs restore_test.sh with
    # no BACKUP_DIR, and /data/backup does not exist on the host.
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    for name in ["backup.sh", "restore_test.sh"]:
        text = (root / "infra/backup" / name).read_text()
        assert 'BACKUP_DIR="${BACKUP_DIR:-data/backup}"' in text, name


def test_backup_includes_library_without_media() -> None:
    # SEC-43: books and notes are backed up; re-creatable media (audio, video) is not.
    script = (REPO_ROOT / "infra/backup/backup.sh").read_text()
    restic_lines = [
        ln for ln in script.splitlines() if ln.strip().startswith("restic") and " backup " in ln
    ]
    assert len(restic_lines) == 1
    assert '"$LIBRARY_DIR"' in restic_lines[0]
    assert 'LIBRARY_DIR="${LIBRARY_DIR:-data/library}"' in script
    assert "--exclude-file infra/backup/restic-excludes.txt" in restic_lines[0]

    excludes = (REPO_ROOT / "infra/backup/restic-excludes.txt").read_text().splitlines()
    assert "data/library/media" in excludes or "data/library/media/" in excludes
    # Honeytoken decoys stay excluded.
    assert "aws_root_key.txt" in excludes and ".env.production" in excludes
