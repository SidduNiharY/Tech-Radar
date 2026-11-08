"""Tests for honeytoken generation, exclusions, and confidentiality."""

import os
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.plant_honeytokens import plant, plant_files, verify  # noqa: E402


class FakeDB:
    """Mock database connection that captures SQL queries and last password."""

    def __init__(self) -> None:
        self.last_password: str | None = None
        self.queries: list[str] = []

    def execute(self, sql: str) -> None:
        self.queries.append(sql)
        match = re.search(r"PASSWORD '([^']+)'", sql)
        if match:
            self.last_password = match.group(1)

    def commit(self) -> None:
        pass


def test_backup_excludes_honeytokens() -> None:
    sh = (REPO_ROOT / "infra/backup/backup.sh").read_text()
    assert "--exclude-table-data=techradar.bank_credentials" in sh
    assert "/var/lib/techradar-honey/excludes.txt" in sh


def test_aide_config_excludes_honeytokens() -> None:
    conf = (REPO_ROOT / "infra/host/aide/techradar.conf").read_text()
    assert "/var/lib/techradar-honey/excludes.txt" in conf


def test_plant_script_never_prints_values(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    fake_db = FakeDB()
    plant(tmp_path, fake_db, files=True, db=True)
    out = capsys.readouterr().out

    assert "AKIA" not in out
    assert fake_db.last_password is not None
    assert fake_db.last_password not in out
    assert "Created role admin_backup" in out
    assert "Planted table techradar.bank_credentials (5 rows)" in out


def test_plant_files_permissions_and_verify(tmp_path: Path) -> None:
    plant_files(tmp_path)

    aws_key = tmp_path / "secrets" / "aws_root_key.txt"
    assert aws_key.exists()
    assert (os.stat(aws_key).st_mode & 0o777) == 0o600
    assert aws_key.read_text().startswith("AKIA")

    env_prod = tmp_path / ".env.production"
    assert env_prod.exists()
    assert (os.stat(env_prod).st_mode & 0o777) == 0o600
    assert "DATABASE_URL=postgresql://admin_backup:" in env_prod.read_text()

    assert verify(tmp_path) is True

    # Intentionally weaken permissions and verify detection
    os.chmod(aws_key, 0o644)
    assert verify(tmp_path) is False


def test_audit_rules_contain_honeytokens() -> None:
    rules = (REPO_ROOT / "infra/host/audit/techradar.rules").read_text()
    assert "tr_secret_change" in rules
    assert "tr_sudoers" in rules
    assert "tr_ssh" in rules
    assert "tr_honey" in rules
