from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def test_simulate_script_covers_every_phase1_attack():
    sh = (REPO_ROOT / "security/simulate/phase1.sh").read_text()
    for needle in [
        "exec -T bot sh",
        "aws_root_key",
        "admin_backup",
        "create_connection",
        "egress-probe",
        "techradar-aide",
        "--pinned-override",
        "--gpus all",
    ]:
        assert needle in sh, f"Missing attack simulation needle: {needle}"


def test_simulate_script_covers_every_phase2_attack():
    sh = (REPO_ROOT / "security/simulate/phase2.sh").read_text()
    for needle in [
        "pdf_with_js.pdf",
        "renamed_exe.pdf",
        "clamav",
        "quarantined",
        "rejected",
    ]:
        assert needle in sh, f"Missing attack simulation needle: {needle}"


ALERT = (
    '{{"level":"critical","source":"auditd","rule":"tr_honey",'
    '"service":null,"summary":"x","at":"{at}"}}'
)


def _wait_for_alert_fn() -> str:
    import re

    sh = (REPO_ROOT / "security/simulate/phase1.sh").read_text()
    start = sh.index("alert_seen() {")
    match = re.search(r"wait_for_alert\(\)\s*\{.*?\n\}", sh[start:], re.DOTALL)
    assert match, "wait_for_alert not found"
    return sh[start : start + match.end()]


def _run_wait(tmp_path, log_lines, rule, level, sim_start):
    import subprocess

    log = tmp_path / "alerts.jsonl"
    log.write_text("".join(x + "\n" for x in log_lines))
    script = (
        f"{_wait_for_alert_fn()}\n"
        f'ALERT_LOG="{log}"\nSIM_START="{sim_start}"\n'
        f'wait_for_alert "{rule}" "{level}" 1'
    )
    r = subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=False)  # noqa: S603, S607
    return r.returncode


def test_wait_for_alert_reads_the_compact_json_the_alerter_writes(tmp_path):
    # AlertLog writes model_dump_json() (no spaces); the old grep looked for
    # '"rule": "x"' with a space and could never match.
    line = ALERT.format(at="2026-11-13T02:10:00Z")
    assert _run_wait(tmp_path, [line], "tr_honey", "critical", "2026-11-13T02:00:00+00:00") == 0


def test_wait_for_alert_ignores_alerts_from_before_the_run(tmp_path):
    old = ALERT.format(at="2026-11-12T23:00:00Z")
    assert _run_wait(tmp_path, [old], "tr_honey", "critical", "2026-11-13T02:00:00+00:00") != 0
