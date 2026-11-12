"""`make security` and the gates must run what the overview's gate table says.

Before, `make security` ran only the three check_* scripts and two test
files, gate-1 skipped the db, egress, restore, host and attack checks, and
gates 3, 4 and 5 did not include the earlier gates.
"""

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def dry_run(target: str) -> str:
    r = subprocess.run(["make", "-n", target], cwd=ROOT, capture_output=True, text=True, check=True)
    return r.stdout


@pytest.mark.parametrize(
    "needle",
    [
        "--from semgrep==1.184.0",
        "semgrep --test security/semgrep",
        "semgrep scan --error --config security/semgrep/rules.yaml",
        "gitleaks",
        "osv-scanner",
        "trivy config",
        "hadolint",
        "shellcheck",
        "check_deps.py",
        "check_mcp.py",
        "check_skills.py",
        "test_compose_policy.py",
    ],
)
def test_security_runs_every_scanner(needle: str):
    assert needle in dry_run("security")


@pytest.mark.parametrize(
    "needle",
    [
        "ruff check",
        "-m db",
        "-m egress",
        "tests/hostsec",
        "restore_test.sh",
        "check_host.sh",
        "security/simulate/phase1.sh",
        "trivy image",
    ],
)
def test_gate1_runs_the_plan_checks(needle: str):
    assert needle in dry_run("gate-1")


@pytest.mark.parametrize(
    ("gate", "earlier_marker"),
    [("gate-3", "tests/library"), ("gate-4", "tests/briefing"), ("gate-5", "tests/api")],
)
def test_later_gates_include_the_earlier_ones(gate: str, earlier_marker: str):
    assert earlier_marker in dry_run(gate)


def test_makefile_has_no_mac_only_paths():
    assert "/opt/homebrew" not in (ROOT / "Makefile").read_text(encoding="utf-8")
