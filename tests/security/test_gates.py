"""Tests verifying verification gates in Makefile."""

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MAKEFILE_PATH = REPO_ROOT / "Makefile"

DEFINED_GATES = [
    "gate-1",
    "gate-2",
    "gate-2b",
    "gate-2c",
    "gate-3",
    "gate-4",
]


@pytest.mark.parametrize("gate", DEFINED_GATES)
def test_makefile_contains_gate_target(gate: str) -> None:
    content = MAKEFILE_PATH.read_text(encoding="utf-8")
    assert f"{gate}:" in content, f"Makefile is missing target definition for '{gate}:'"


def test_makefile_contains_all_defined_gates() -> None:
    content = MAKEFILE_PATH.read_text(encoding="utf-8")
    for gate in DEFINED_GATES:
        assert gate in content, f"Makefile is missing '{gate}'"


@pytest.mark.parametrize("gate", ["gate-2c", "gate-3", "gate-4"])
def test_gate_dry_run_exits_zero(gate: str) -> None:
    result = subprocess.run(
        ["make", "-n", gate],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"make -n {gate} failed (exit code {result.returncode}):\n{result.stderr}"
    )
