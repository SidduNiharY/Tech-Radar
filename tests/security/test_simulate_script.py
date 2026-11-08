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
