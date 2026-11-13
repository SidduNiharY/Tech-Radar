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
