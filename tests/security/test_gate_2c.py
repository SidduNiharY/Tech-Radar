"""Gate 2c wiring (Phase 2c Task 11): Makefile targets, the attack simulation, the big PDF.

On 2026-11-14 `gate-2c` still ran `tests/rag/test_scoped_ask.py`, a file deleted when
Task 8 replaced the substring scope with an exact `doc_id` filter, so the gate could
never pass. These tests keep the gate pointing at files that exist and running every
step of the gates before it.
"""

from __future__ import annotations

import inspect
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MAKEFILE = ROOT / "Makefile"
SIM = ROOT / "security/simulate/phase2c.sh"


def dry_run(target: str) -> str:
    r = subprocess.run(["make", "-n", target], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout


# --- Makefile ---------------------------------------------------------------


def test_makefile_references_only_files_that_exist():
    text = MAKEFILE.read_text(encoding="utf-8")
    paths = set(re.findall(r"(?<![\w/])(?:tests|security|scripts|evals|infra)/[\w./-]*\w", text))
    missing = sorted(p for p in paths if "*" not in p and not (ROOT / p).exists())
    assert not missing, f"Makefile names missing files: {missing}"


def test_gate_2c_keeps_every_step_of_gate_2b():
    earlier = [line for line in dry_run("gate-2b").splitlines() if line.strip()]
    gate = dry_run("gate-2c")
    for line in earlier:
        assert line in gate, f"gate-2c lost a gate-2b step: {line}"


@pytest.mark.parametrize(
    "needle",
    [
        "tests/library",
        "tests/intake",
        "tests/night",
        "tests/ops",
        "tests/parser",
        "tests/pipeline",
        "tests/evals",
        "tests/rag/test_retrieve_scope.py",
        "-m db",
        "-m slow",
        "evals/rag/run.py",
        "bash security/simulate/phase2c.sh",
        "tests/security/test_compose_policy.py",
        "tests/security/test_falco_rules.py",
        "tests/security/test_gate_2c.py",
        "WAITING: internet stage",
        "GATE 2c",
    ],
)
def test_gate_2c_runs_the_plan_checks(needle: str):
    assert needle in dry_run("gate-2c")


def test_simulate_2c_target_runs_the_script():
    assert "bash security/simulate/phase2c.sh" in dry_run("simulate-2c")


def test_gate_3_includes_gate_2c():
    assert "security/simulate/phase2c.sh" in dry_run("gate-3")


def test_gate_1_mac_still_runs_no_simulation():
    assert "phase2c" not in dry_run("gate-1-mac")


def test_parser_timeout_stays_120_seconds():
    # SEC-06: AGENTS.md rule 3. The gate must never be "fixed" by raising it.
    from techradar.parser.limits import run_with_limits
    from techradar.settings import Settings

    assert Settings.model_fields["parse_timeout_s"].default == 120
    assert inspect.signature(run_with_limits).parameters["timeout_s"].default == 120


# --- security/simulate/phase2c.sh -----------------------------------------------


def test_simulation_script_parses():
    r = subprocess.run(["bash", "-n", str(SIM)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


@pytest.mark.parametrize(
    "needle",
    [
        "set -euo pipefail",
        "--network none",
        "--pull never",
        "--read-only",
        "--cap-drop ALL",
        "no-new-privileges",
        "mktemp -d",
        "trap cleanup EXIT",
        "zip_bomb.docx",
        "ratio_bomb.docx",
        "macro.docx",
        "entity_bomb.epub",
        "playlist.mp4",
        "ftyp_playlist.mp4",
        "big_300_pages.pdf",
        "pdf_with_js.pdf",
        "oversized.pdf",
        "os.symlink",
        "quarantine",
        "reject",
    ],
)
def test_simulation_covers_every_attack(needle: str):
    assert needle in SIM.read_text(encoding="utf-8")


def test_simulation_never_touches_real_data_or_the_database():
    sh = SIM.read_text(encoding="utf-8")
    for forbidden in ["./data", "data/library-inbox", "postgres", "docker compose", "secrets/"]:
        assert forbidden not in sh, forbidden


def _local_python() -> str | None:
    venv = ROOT / ".venv/bin/python"
    return str(venv) if venv.exists() else None


@pytest.mark.slow
def test_simulation_passes_locally_against_the_real_gateway(tmp_path):
    # Dev check only: the gateway and inbox code run with this repo's Python instead
    # of the parser image. The gate run is `bash security/simulate/phase2c.sh` on the
    # server, in the parser image with --network none.
    py = _local_python()
    if py is None or shutil.which("ffprobe") is None:
        pytest.skip("needs .venv and ffprobe")
    env = {**os.environ, "TR_SIM_PYTHON": py, "TMPDIR": str(tmp_path)}
    r = subprocess.run(
        ["bash", str(SIM)], cwd=ROOT, env=env, capture_output=True, text=True, timeout=600
    )
    assert r.returncode == 0, r.stdout[-4000:] + r.stderr[-2000:]
    assert "FAIL" not in r.stdout
    assert "LOCAL MODE" in r.stdout
    assert list(tmp_path.iterdir()) == [], "the simulation left files behind"


# --- scripts/make_big_pdf.py ----------------------------------------------------


def _make_pdf(out: Path) -> bytes:
    r = subprocess.run(
        [_local_python() or "python3", "scripts/make_big_pdf.py", "--out", str(out)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr
    return out.read_bytes()


def test_big_pdf_is_deterministic_and_clean(tmp_path):
    from techradar.intake.pdfscan import check_pdf

    a = _make_pdf(tmp_path / "a.pdf")
    b = _make_pdf(tmp_path / "b.pdf")
    assert a == b
    assert a.startswith(b"%PDF-1.4")
    assert check_pdf(a).outcome == "ok"


def test_big_pdf_has_300_pages_chapters_and_page_text(tmp_path):
    pdfium = pytest.importorskip("pypdfium2")
    from techradar.parser.pdf import pdf_probe

    out = tmp_path / "big.pdf"
    _make_pdf(out)
    probe = pdf_probe(out)
    assert probe.n_pages == 300
    chapters = [(e.title, e.page) for e in probe.outline if e.level == 1]
    assert len(chapters) == 10
    assert chapters[0] == ("Chapter 1: Packets and Protocols", 1)
    assert chapters[4][1] == 121  # chapters are 30 pages, not aligned to 25-page parts
    pdf = pdfium.PdfDocument(out)
    first = pdf[0].get_textpage().get_text_range()
    assert "Chapter 1: Packets and Protocols" in first
    page_157 = pdf[156].get_textpage().get_text_range()
    assert "Page 157" in page_157 and "Chapter 6" in page_157
    assert "fact-157" in page_157
    assert len(page_157) >= 200  # above the parser's MIN_TEXT_CHARS


def test_big_pdf_default_path_is_git_ignored():
    r = subprocess.run(
        ["git", "check-ignore", "-q", "tests/fixtures/library/big_300_pages.pdf"], cwd=ROOT
    )
    assert r.returncode == 0
