"""Tests for filesystem integrity, image digest pinning, and integrity_check CLI."""

import json
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.integrity_check import check_integrity, parse_overrides  # noqa: E402
from techradar.hostsec.integrity import (  # noqa: E402
    digest_mismatches,
    parse_docker_diff,
    unexpected_changes,
)


def test_unexpected_changes_ignore_tmpfs_and_volumes() -> None:
    ch = parse_docker_diff("C /tmp\nA /tmp/x\nA /usr/bin/evil\nC /data/raw/a\n")
    assert unexpected_changes(ch, ["/tmp"], ["/data/raw"]) == ["/usr/bin/evil"]  # noqa: S108


def test_digest_mismatch() -> None:
    assert digest_mismatches(
        {"postgres": "sha256:aa", "bot": "sha256:cc"},
        {"postgres": "sha256:bb", "bot": "sha256:cc"},
    ) == ["postgres"]


def test_parse_docker_diff_actions_and_whitespace() -> None:
    raw = """
    A /var/log/app.log
    C /etc/hosts
    D /etc/old.conf
    X /invalid/action

    """
    parsed = parse_docker_diff(raw)
    assert parsed == [
        ("A", "/var/log/app.log"),
        ("C", "/etc/hosts"),
        ("D", "/etc/old.conf"),
    ]


def test_unexpected_changes_all_expected() -> None:
    ch = parse_docker_diff("A /tmp/cache/item\nC /tmp\nC /var/log/squid/access.log\n")
    assert unexpected_changes(ch, ["/tmp", "/var/log/squid"], []) == []  # noqa: S108


def test_digest_mismatches_all_matching() -> None:
    running = {"svc1": "sha256:111", "svc2": "sha256:222"}
    pinned = {"svc1": "sha256:111", "svc2": "sha256:222"}
    assert digest_mismatches(running, pinned) == []


def test_parse_overrides() -> None:
    items = ["postgres=sha256:mismatch", "bot=sha256:custom"]
    overrides = parse_overrides(items)
    assert overrides == {
        "postgres": "sha256:mismatch",
        "bot": "sha256:custom",
    }


def test_check_integrity_simulation(tmp_path: Path) -> None:
    compose_yaml = tmp_path / "compose.yaml"
    compose_yaml.write_text("""
services:
  web:
    image: test/web:1.0@sha256:expectedweb
    tmpfs:
      - /tmp
    volumes:
      - ./data:/app/data
""")

    # Mock runner
    def fake_runner(cmd: Sequence[str]) -> subprocess.CompletedProcess[str]:
        cmd_list = list(cmd)
        if cmd_list == ["docker", "compose", "ps", "--services", "--filter", "status=running"]:
            return subprocess.CompletedProcess(cmd_list, 0, stdout="web\n", stderr="")
        if cmd_list == ["docker", "compose", "ps", "-q", "web"]:
            return subprocess.CompletedProcess(cmd_list, 0, stdout="cid-web-123\n", stderr="")
        if cmd_list == ["docker", "inspect", "cid-web-123"]:
            data = [{"Image": "sha256:expectedweb"}]
            return subprocess.CompletedProcess(cmd_list, 0, stdout=json.dumps(data), stderr="")
        if cmd_list == ["docker", "diff", "cid-web-123"]:
            diff = "C /tmp\nA /tmp/temp.txt\nA /app/data/file.txt\nA /etc/backdoor\n"
            return subprocess.CompletedProcess(cmd_list, 0, stdout=diff, stderr="")
        return subprocess.CompletedProcess(cmd_list, 1, stdout="", stderr="command not found")

    code, lines = check_integrity(
        compose_file=compose_yaml,
        built_images_file=None,
        runner=fake_runner,
    )
    assert code == 1
    assert any("CRITICAL web unexpected changes: /etc/backdoor" in line for line in lines)


def test_check_integrity_ok_and_override_mismatch(tmp_path: Path) -> None:
    compose_yaml = tmp_path / "compose.yaml"
    compose_yaml.write_text("""
services:
  app:
    image: test/app:1.0@sha256:expectedapp
    tmpfs:
      - /tmp
""")

    def fake_runner(cmd: Sequence[str]) -> subprocess.CompletedProcess[str]:
        cmd_list = list(cmd)
        if cmd_list == ["docker", "compose", "ps", "--services", "--filter", "status=running"]:
            return subprocess.CompletedProcess(cmd_list, 0, stdout="app\n", stderr="")
        if cmd_list == ["docker", "compose", "ps", "-q", "app"]:
            return subprocess.CompletedProcess(cmd_list, 0, stdout="cid-app-456\n", stderr="")
        if cmd_list == ["docker", "inspect", "cid-app-456"]:
            data = [{"Image": "sha256:expectedapp"}]
            return subprocess.CompletedProcess(cmd_list, 0, stdout=json.dumps(data), stderr="")
        if cmd_list == ["docker", "diff", "cid-app-456"]:
            return subprocess.CompletedProcess(cmd_list, 0, stdout="A /tmp/cache\n", stderr="")
        return subprocess.CompletedProcess(cmd_list, 1, stdout="", stderr="")

    # 1. Without overrides -> OK
    code, lines = check_integrity(
        compose_file=compose_yaml,
        built_images_file=None,
        runner=fake_runner,
    )
    assert code == 0
    assert lines == ["OK app"]

    # 2. With override -> CRITICAL digest mismatch
    code, lines = check_integrity(
        compose_file=compose_yaml,
        built_images_file=None,
        pinned_overrides={"app": "sha256:overridden_different"},
        runner=fake_runner,
    )
    assert code == 1
    assert "CRITICAL app digest mismatch" in lines
