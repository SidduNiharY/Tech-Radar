from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def test_check_host_has_new_checks():
    sh = (REPO_ROOT / "infra/host/check_host.sh").read_text()
    for needle in [
        "systemctl get-default",
        "tailscale lock status",
        "falco-modern-bpf",
        "techradar-alerter",
        "techradar-heartbeat.timer",
    ]:
        assert needle in sh, f"Missing {needle} in infra/host/check_host.sh"
