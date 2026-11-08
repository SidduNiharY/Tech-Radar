"""Tests for containment response, forensic evidence collection, and fake runners."""

import json
import subprocess
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import pytest

from techradar.hostsec.alerts import Alert, Level
from techradar.hostsec.contain import (
    collect_evidence,
    contain,
    respond,
)

PUB = Path("infra/host/evidence.pub.example")
NOW = datetime(2026, 11, 8, 10, 0, tzinfo=UTC)


def critical(
    service: str | None = None,
    rule: str = "critical rule",
    summary: str = "critical summary",
) -> Alert:
    return Alert(
        level=Level.CRITICAL,
        source="alerter",
        rule=rule,
        service=service,
        summary=summary,
        at=NOW,
    )


def warning(
    service: str | None = None,
    rule: str = "warning rule",
    summary: str = "warning summary",
) -> Alert:
    return Alert(
        level=Level.WARNING,
        source="alerter",
        rule=rule,
        service=service,
        summary=summary,
        at=NOW,
    )


class FakeRunner:
    def __init__(self, networks: Sequence[str] = ("techradar-net",)) -> None:
        self.calls: list[list[str]] = []
        self.networks = list(networks)

    def __call__(
        self,
        args: list[str],
        *,
        timeout_s: int = 60,
    ) -> subprocess.CompletedProcess:
        self.calls.append(list(args))
        stdout = ""
        if len(args) >= 2 and args[0] == "docker" and args[1] == "inspect":
            stdout = json.dumps([
                {
                    "NetworkSettings": {
                        "Networks": {net: {} for net in self.networks},
                    },
                }
            ])
        elif len(args) >= 2 and args[0] == "docker" and args[1] == "diff":
            stdout = "C /etc/shadow\nA /tmp/evil\n"
        elif len(args) >= 3 and args[0:3] == ["docker", "compose", "logs"]:
            stdout = "sample log lines\n"

        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout=stdout,
            stderr="",
        )


@pytest.fixture
def fake_runner() -> FakeRunner:
    return FakeRunner()


def test_evidence_saved_before_stop(fake_runner: FakeRunner, tmp_path: Path) -> None:
    res = respond(
        critical(service="parser"),
        "on",
        fake_runner,
        out_root=tmp_path,
        pubkey=PUB,
        falco_events=[],
    )
    assert res == "contained after saving evidence"
    calls = fake_runner.calls
    diff_at = next(i for i, c in enumerate(calls) if c[1] == "diff")
    first_disconnect = next(
        i for i, c in enumerate(calls) if c[1:3] == ["network", "disconnect"]
    )
    assert diff_at < first_disconnect and calls[-1][-2:] == ["stop", "parser"]


def test_alert_only_mode_never_contains(
    fake_runner: FakeRunner,
    tmp_path: Path,
) -> None:
    assert (
        respond(
            critical(service="parser"),
            "alert-only",
            fake_runner,
            out_root=tmp_path,
            pubkey=PUB,
            falco_events=[],
        )
        == "alert only"
    )
    assert not any("stop" in c for c in fake_runner.calls)


def test_warning_never_contains(fake_runner: FakeRunner, tmp_path: Path) -> None:
    assert (
        respond(
            warning(service="parser"),
            "on",
            fake_runner,
            out_root=tmp_path,
            pubkey=PUB,
            falco_events=[],
        )
        == "alert only"
    )
    assert not any("stop" in c for c in fake_runner.calls)


def test_host_alert_without_service_never_contains(
    fake_runner: FakeRunner,
    tmp_path: Path,
) -> None:
    assert (
        respond(
            critical(service=None),
            "on",
            fake_runner,
            out_root=tmp_path,
            pubkey=PUB,
            falco_events=[],
        )
        == "alert only"
    )
    assert not any("stop" in c for c in fake_runner.calls)


def test_contain_runs_disconnect_for_all_networks(
    fake_runner: FakeRunner,
) -> None:
    fake_runner.networks = ["net-a", "net-b"]
    cmds = contain("fetcher", fake_runner)
    assert ["docker", "network", "disconnect", "net-a", "fetcher"] in cmds
    assert ["docker", "network", "disconnect", "net-b", "fetcher"] in cmds
    assert cmds[-1] == ["docker", "compose", "stop", "fetcher"]


def test_collect_evidence_creates_encrypted_files(
    fake_runner: FakeRunner,
    tmp_path: Path,
) -> None:
    evidence = collect_evidence(
        "parser",
        fake_runner,
        tmp_path,
        PUB,
        falco_events=["falco event line 1"],
        now=NOW,
    )
    assert evidence.dir.exists()
    assert (evidence.dir.stat().st_mode & 0o777) == 0o700
    # Encrypted files created and plain files removed
    for f in evidence.files:
        assert f.endswith(".age")
        enc_file = evidence.dir / f
        assert enc_file.exists()
        assert (enc_file.stat().st_mode & 0o777) == 0o400
