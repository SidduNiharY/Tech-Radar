"""Tests for resource watcher: GPU, restart loops, and outbound bytes."""

from datetime import UTC, datetime, timedelta

from techradar.hostsec.resources import (
    GpuApp,
    check_gpu,
    check_gpu_busy,
    check_outbound_bytes,
    check_restarts,
    parse_gpu_apps,
    service_of_pid,
)

NOW = datetime(2026, 11, 8, 10, 0, tzinfo=UTC)


def test_parse_gpu_apps() -> None:
    assert parse_gpu_apps("4242, ollama, 3200\n") == [
        GpuApp(pid=4242, name="ollama", used_mib=3200)
    ]
    multi = "101, ollama, 4096\n102, python, 1024\n\n"
    assert parse_gpu_apps(multi) == [
        GpuApp(pid=101, name="ollama", used_mib=4096),
        GpuApp(pid=102, name="python", used_mib=1024),
    ]
    assert parse_gpu_apps("") == []


def test_service_of_pid() -> None:
    containers = {
        "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890": "ollama",
        "1234567890ab": "voice-worker",
    }
    cgroup_v2 = (
        "0::/system.slice/docker-abcdef1234567890"
        "abcdef1234567890abcdef1234567890abcdef1234567890.scope\n"
    )
    assert service_of_pid(42, cgroup_v2, containers) == "ollama"

    cgroup_v1 = "1:name=systemd:/docker/1234567890abcdef\n"
    assert service_of_pid(43, cgroup_v1, containers) == "voice-worker"

    cgroup_host = "0::/user.slice/user-1000.slice/session-1.scope\n"
    assert service_of_pid(44, cgroup_host, containers) is None


def test_unknown_gpu_process_is_critical() -> None:
    assert check_gpu([GpuApp(pid=7, name="xmrig", used_mib=900)], {7: None}) == [
        "CRITICAL unknown GPU process: xmrig"
    ]


def test_allowed_gpu_services_no_alert() -> None:
    apps = [
        GpuApp(pid=10, name="ollama", used_mib=4000),
        GpuApp(pid=20, name="python", used_mib=1200),
    ]
    services = {10: "ollama", 20: "voice-worker"}
    assert check_gpu(apps, services) == []


def test_unallowed_service_gpu_is_critical() -> None:
    apps = [GpuApp(pid=30, name="python", used_mib=1000)]
    services = {30: "bot"}
    assert check_gpu(apps, services) == ["CRITICAL unknown GPU process: python"]


def test_gpu_busy_with_no_job() -> None:
    assert check_gpu_busy([95] * 15, [], voice_running=False) == "WARNING GPU busy with no job"
    assert check_gpu_busy([95] * 15, ["qwen3.5:4b"], voice_running=False) is None
    assert check_gpu_busy([95] * 15, [], voice_running=True) is None
    assert check_gpu_busy([75] * 15, [], voice_running=False) is None
    assert check_gpu_busy([], [], voice_running=False) is None


def test_restart_loop() -> None:
    prev = {"bot": (1, NOW)}
    assert check_restarts(prev, {"bot": 4}, NOW + timedelta(minutes=5)) == [
        "WARNING bot restarting"
    ]
    # Less than 3 restarts: no alert
    assert check_restarts(prev, {"bot": 3}, NOW + timedelta(minutes=5)) == []
    # Outside 10 minutes: no alert
    assert check_restarts(prev, {"bot": 5}, NOW + timedelta(minutes=15)) == []


def test_outbound_bytes() -> None:
    line = (
        "1762590000.123 10 172.28.0.5 TCP_MISS/200 250000000 CONNECT "
        "api.telegram.org:443 - DIRECT/- -"
    )
    client_map = {"172.28.0.5": "bot"}
    assert check_outbound_bytes([line], client_map) == ["WARNING bot sent 250 MB in an hour"]

    # Under 200MB limit: no alert
    under_limit_line = (
        "1762590000.123 10 172.28.0.5 TCP_MISS/200 150000000 CONNECT "
        "api.telegram.org:443 - DIRECT/- -"
    )
    assert check_outbound_bytes([under_limit_line], client_map) == []


def test_package_does_not_preload_modules_run_with_python_m():
    # The timers run `python -m techradar.hostsec.resources` and `.alerter`.
    # If the package __init__ imports them first, Python warns on every run.
    import ast
    from pathlib import Path

    init = Path(__file__).resolve().parents[2] / "src/techradar/hostsec/__init__.py"
    tree = ast.parse(init.read_text(encoding="utf-8"))
    imported = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert "techradar.hostsec.resources" not in imported
    assert "techradar.hostsec.alerter" not in imported
