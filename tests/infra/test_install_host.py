"""infra/host/install_host.sh installs the host units with the real paths.

The unit files in the repo name /home/techradar/TechRadarBrain and the user
`techradar`, and the backup unit names /opt/techradar. On the server the
repo lives in the owner's home under their own user name, so copying the
files as they are would give units that cannot start. The installer writes
them with the real repo path and owner. DESTDIR lets this test run it
without root.
"""

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "infra" / "host" / "install_host.sh"

UNITS = [
    "techradar-alerter.service",
    "techradar-heartbeat.service",
    "techradar-heartbeat.timer",
    "techradar-aide.service",
    "techradar-aide.timer",
    "techradar-integrity.service",
    "techradar-integrity.timer",
    "techradar-lynis.service",
    "techradar-lynis.timer",
    "techradar-resources.service",
    "techradar-resources.timer",
    "techradar-backup.service",
    "techradar-backup.timer",
]


def run_install(tmp_path: Path) -> Path:
    dest = tmp_path / "root"
    subprocess.run(  # noqa: S603
        ["bash", str(SCRIPT)],
        env={"PATH": "/usr/bin:/bin", "DESTDIR": str(dest), "REPO": "/srv/tr", "OWNER": "alice"},
        check=True,
        capture_output=True,
        text=True,
    )
    return dest


def installed_files(dest: Path) -> list[Path]:
    return [p for p in dest.rglob("*") if p.is_file()]


def test_every_unit_is_installed(tmp_path):
    dest = run_install(tmp_path)
    for unit in UNITS:
        assert (dest / "etc/systemd/system" / unit).is_file(), unit
    assert (dest / "etc/audit/rules.d/techradar.rules").is_file()
    assert (dest / "etc/aide/techradar.conf").is_file()


def test_no_placeholder_paths_or_users_remain(tmp_path):
    dest = run_install(tmp_path)
    for f in installed_files(dest):
        text = f.read_text(encoding="utf-8")
        assert "/home/techradar" not in text, f
        assert "/opt/techradar" not in text, f
        assert "User=techradar" not in text, f


def test_units_use_the_real_repo_and_owner(tmp_path):
    dest = run_install(tmp_path)
    alerter = (dest / "etc/systemd/system/techradar-alerter.service").read_text()
    assert "User=alice" in alerter
    assert "ExecStart=/srv/tr/.venv/bin/python -m techradar.hostsec.alerter" in alerter
    backup = (dest / "etc/systemd/system/techradar-backup.service").read_text()
    assert "WorkingDirectory=/srv/tr" in backup
    rules = (dest / "etc/audit/rules.d/techradar.rules").read_text()
    assert "-w /srv/tr/secrets -p wa" in rules
    assert "-w /home/alice/.ssh/authorized_keys" in rules


def test_aide_reads_the_installed_config(tmp_path):
    dest = run_install(tmp_path)
    aide = (dest / "etc/systemd/system/techradar-aide.service").read_text()
    assert "--config /etc/aide/techradar.conf" in aide
    conf = (dest / "etc/aide/techradar.conf").read_text()
    assert "/srv/tr/compose.yaml" in conf


def test_installer_refuses_without_root_or_destdir():
    r = subprocess.run(  # noqa: S603
        ["bash", str(SCRIPT)],
        env={"PATH": "/usr/bin:/bin", "REPO": "/srv/tr", "OWNER": "alice"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode != 0


def test_host_units_that_read_secrets_point_at_the_repo_secrets(tmp_path):
    # Outside Docker there is no /run/secrets (the Settings default).
    dest = run_install(tmp_path)
    for unit in ["techradar-alerter.service", "techradar-heartbeat.service"]:
        text = (dest / "etc/systemd/system" / unit).read_text()
        assert "Environment=TR_SECRETS_DIR=/srv/tr/secrets" in text, unit
