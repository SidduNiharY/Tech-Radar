from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def test_simulate_script_covers_every_phase1_attack():
    sh = (REPO_ROOT / "security/simulate/phase1.sh").read_text()
    for needle in [
        "exec -T postgres sh",
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


def test_every_attack_waits_for_a_rule_the_parsers_really_produce():
    # On 2026-11-13 attacks 3, 6, 7 and 8 waited for rule names no parser
    # produced, so they could never pass. Each sample is what the real source
    # emits for that attack; the parsed rule must be what phase1.sh waits for.
    import json
    import re

    from techradar.hostsec.sources import from_falco, from_journal, from_postgres, from_squid

    sh = (REPO_ROOT / "security/simulate/phase1.sh").read_text()
    waited = set(re.findall(r'wait_for_alert "([^"]+)" "([a-z]+)"', sh))

    def falco(rule):
        return json.dumps(
            {
                "rule": rule,
                "priority": "Critical",
                "output": "x",
                "output_fields": {"container.name": "techradar-postgres-1"},
            }
        )

    produced = [
        from_falco(falco("TR shell or package manager in container")),
        from_journal(
            {"SYSLOG_IDENTIFIER": "audit", "MESSAGE": 'type=SYSCALL comm="cat" key="tr_honey"'}
        ),
        from_postgres(
            "2026-11-13 02:00:00.000 UTC [77] FATAL:  "
            'password authentication failed for user "admin_backup"'
        ),
        from_falco(falco("TR connection outside allowed peers")),
        from_squid(
            "1794514104.903 0 10.250.10.20 TCP_DENIED/403 3352 CONNECT evil.example:443 - x",
            {"10.250.10.20": "egress-probe"},
        ),
        from_journal(
            {
                "SYSLOG_IDENTIFIER": "aide",
                "MESSAGE": "AIDE found differences between database and filesystem!!",
            }
        ),
        from_journal(
            {
                "SYSLOG_IDENTIFIER": "techradar-integrity",
                "MESSAGE": "CRITICAL postgres digest mismatch",
            }
        ),
        from_journal(
            {
                "SYSLOG_IDENTIFIER": "techradar-resources",
                "MESSAGE": "CRITICAL unknown GPU process: sleep",
            }
        ),
    ]
    got = {(a.rule, a.level.value) for a in produced if a is not None}
    assert waited == got


def test_attack_output_that_the_alerter_reads_from_the_journal_goes_there():
    sh = (REPO_ROOT / "security/simulate/phase1.sh").read_text()
    assert "systemd-cat -t techradar-integrity" in sh


def test_admin_backup_attack_goes_through_password_auth():
    # Inside the postgres container 127.0.0.1 uses trust auth (seen on the TUF
    # 2026-11-13), so the attack must come from another container.
    sh = (REPO_ROOT / "security/simulate/phase1.sh").read_text()
    assert "psql -h 127.0.0.1 -U admin_backup" not in sh
    assert "host='postgres', user='admin_backup', password='wrong'" in sh


def test_simulation_never_needs_the_network_to_run_its_own_code():
    # 2026-11-13: `uv run` tried to rebuild the project and fetch hatchling
    # from PyPI; with DNS down, attack 7 never ran. The repo's .venv is used.
    sh = (REPO_ROOT / "security/simulate/phase1.sh").read_text()
    assert "uv run" not in sh
    assert ".venv/bin/python scripts/integrity_check.py" in sh


def test_gpu_attack_needs_the_image_already_pulled():
    # Pulling inside the 60-second wait failed (DNS down). The script now
    # checks first and says what to do instead of timing out.
    sh = (REPO_ROOT / "security/simulate/phase1.sh").read_text()
    assert 'docker image inspect "$CUDA_IMAGE"' in sh
    assert "--pull never" in sh
