import os
import re
import stat
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
HOST_DIR = REPO_ROOT / "infra" / "host"
CHECK_HOST_SCRIPT = HOST_DIR / "check_host.sh"
RUNBOOK_FILE = HOST_DIR / "RUNBOOK.md"


def test_runbook_exists_and_covers_all_host_hardening_requirements() -> None:
    assert RUNBOOK_FILE.exists(), f"{RUNBOOK_FILE} must exist"
    content = RUNBOOK_FILE.read_text(encoding="utf-8")

    # 1. Timezone
    assert "Asia/Kolkata" in content
    assert "timedatectl set-timezone Asia/Kolkata" in content

    # 2. Automatic updates
    assert "unattended-upgrades" in content

    # 3. Firewall
    assert "ufw default deny incoming" in content
    assert "ufw default allow outgoing" in content
    assert "ufw" in content and "enable" in content

    # 4. Tailscale
    assert "tailscale up --ssh" in content
    assert "device approval" in content.lower() or "device authorization" in content.lower()
    assert "key expiry" in content.lower()
    assert "funnel" in content.lower()

    # 5. SSH
    assert "ssh.service" in content or "ListenAddress" in content

    # 6. Docker daemon configuration
    assert "/etc/docker/daemon.json" in content
    assert "log-driver" in content and "json-file" in content
    assert "max-size" in content and "10m" in content
    assert "max-file" in content and "3" in content
    assert "live-restore" in content
    assert "no-new-privileges" in content

    # 7. GPU
    assert "nvidia-smi" in content
    assert "nvidia-container-toolkit" in content or "nvidia container toolkit" in content.lower()

    # 8. Battery charging limit
    assert "asusctl -c 80" in content

    # 9. Lid switch behavior
    assert "HandleLidSwitch=ignore" in content
    assert "HandleLidSwitchExternalPower=ignore" in content
    assert "/etc/systemd/logind.conf" in content

    # 10. Docker group
    assert "$OWNER" in content
    assert "docker" in content

    # 11. Full disk encryption, Secure Boot, AppArmor
    assert "crypt" in content or "LUKS" in content
    assert "mokutil --sb-state" in content
    assert "aa-status" in content

    # 12. Router & network security
    assert "UPnP" in content
    assert "port forward" in content.lower()

    # 13. Dual boot & recovery USB
    assert "dual boot" in content.lower()
    assert "recovery usb" in content.lower()


def test_check_host_script_exists_and_is_executable() -> None:
    assert CHECK_HOST_SCRIPT.exists(), f"{CHECK_HOST_SCRIPT} must exist"
    st = os.stat(CHECK_HOST_SCRIPT)
    assert bool(st.st_mode & stat.S_IXUSR), "check_host.sh must have user executable permission"


def test_check_host_script_has_strict_mode() -> None:
    content = CHECK_HOST_SCRIPT.read_text(encoding="utf-8")
    lines = [line.strip() for line in content.splitlines() if line.strip()]

    assert lines[0] == "#!/bin/bash", "check_host.sh must start with #!/bin/bash"
    assert "set -euo pipefail" in lines, "check_host.sh must include 'set -euo pipefail'"


def test_check_host_bash_syntax_valid() -> None:
    res = subprocess.run(  # noqa: S603
        ["bash", "-n", str(CHECK_HOST_SCRIPT)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, f"bash -n failed: {res.stderr}"


def test_check_host_supports_owner_variable() -> None:
    content = CHECK_HOST_SCRIPT.read_text(encoding="utf-8")
    assert 'OWNER="${OWNER:-' in content, (
        "check_host.sh must support OWNER environment variable override"
    )


def test_check_host_contains_all_12_checks_in_order() -> None:
    content = CHECK_HOST_SCRIPT.read_text(encoding="utf-8")

    patterns = [
        (1, r"ufw"),
        (2, r"ss -ltnH"),
        (3, r"unattended-upgrades"),
        (4, r"tailscale status"),
        (5, r"docker group"),
        (6, r"/etc/docker/daemon\.json"),
        (7, r"aa-status"),
        (8, r"lsblk"),
        (9, r"mokutil.*--sb-state"),
        (10, r"timedatectl|Asia/Kolkata"),
        (11, r"techradar-backup\.timer"),
        (12, r"nvidia-smi"),
    ]

    last_pos = 0
    for idx, pattern in patterns:
        match = re.search(pattern, content[last_pos:])
        assert match is not None, (
            f"Check #{idx} matching {pattern!r} not found after previous checks in check_host.sh"
        )
        last_pos += match.start()


def test_check_host_output_formatting_tags() -> None:
    content = CHECK_HOST_SCRIPT.read_text(encoding="utf-8")
    assert "[PASS]" in content
    assert "[WARN]" in content
    assert "[FAIL]" in content


def test_check_host_is_allowed_ip_logic() -> None:
    # Test the bash IP filtering logic embedded in check_host.sh
    content = CHECK_HOST_SCRIPT.read_text(encoding="utf-8")
    match = re.search(r"(is_allowed_ip\(\)\s*\{.*?\n\})", content, re.DOTALL)
    assert match is not None, "is_allowed_ip function definition not found in check_host.sh"
    func_def = match.group(1)

    test_cases = [
        # (IP, expected_allowed)
        ("127.0.0.1", True),
        ("127.0.0.53", True),
        ("127.255.255.254", True),
        ("::1", True),
        ("100.64.0.1", True),
        ("100.100.50.25", True),
        ("100.127.255.254", True),
        ("fd7a:115c:a1e0::1", True),
        ("FD7A:115C:A1E0:abcd::1", True),
        ("0.0.0.0", False),  # noqa: S104
        ("::", False),
        ("*", False),
        ("100.63.255.255", False),
        ("100.128.0.1", False),
        ("192.168.1.1", False),
        ("10.0.0.1", False),
        ("172.16.0.1", False),
    ]

    for ip, should_allow in test_cases:
        bash_script = f"""{func_def}
if is_allowed_ip "{ip}"; then
    echo "ALLOW"
else
    echo "DENY"
fi
"""
        res = subprocess.run(  # noqa: S603
            ["bash", "-c", bash_script],
            capture_output=True,
            text=True,
            check=False,
        )
        assert res.returncode == 0, f"Error running bash test for {ip}: {res.stderr}"
        expected = "ALLOW" if should_allow else "DENY"
        assert res.stdout.strip() == expected, (
            f"IP {ip} expected {expected} but got {res.stdout.strip()}"
        )


def _bash_function(name: str) -> str:
    content = CHECK_HOST_SCRIPT.read_text(encoding="utf-8")
    match = re.search(rf"({name}\(\)\s*\{{.*?\n\}})", content, re.DOTALL)
    assert match is not None, f"{name} not found in check_host.sh"
    return match.group(1)


def test_listener_ip_parses_ss_local_fields() -> None:
    # Seen on the TUF 2026-11-13: tailscaled's IPv6 listener carries a
    # %interface tag after the bracket and was reported as disallowed.
    cases = {
        "0.0.0.0:8765": "0.0.0.0",  # noqa: S104
        "127.0.0.53%lo:53": "127.0.0.53",
        "[::1]:631": "::1",
        "[fd7a:115c:a1e0::2229:d34f]%tailscale0:61088": "fd7a:115c:a1e0::2229:d34f",
        "100.101.102.103:22": "100.101.102.103",
        "*:22": "*",
        "[::]:22": "::",
    }
    func = _bash_function("listener_ip")
    for field, expected in cases.items():
        res = subprocess.run(  # noqa: S603
            ["bash", "-c", f'{func}\nlistener_ip "{field}"'],
            capture_output=True,
            text=True,
            check=False,
        )
        assert res.stdout.strip() == expected, (field, res.stdout, res.stderr)


def test_daemon_and_timer_checks_need_running_units() -> None:
    # A unit file on disk is not a running monitor: the alerter was reported
    # PASS while switched off, and timers passed when only the repo had them.
    content = CHECK_HOST_SCRIPT.read_text(encoding="utf-8")
    check16 = content[content.index("=== Check 16") : content.index("=== Check 17")]
    check17 = content[content.index("=== Check 17") :]
    assert '-f "/etc/systemd/system/${daemon}.service"' not in check16
    assert "infra/host/timers/${timer_unit}" not in check17
    assert '-f "/etc/systemd/system/${timer_unit}"' not in check17
