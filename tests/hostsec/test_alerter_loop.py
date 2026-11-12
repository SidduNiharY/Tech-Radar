"""The alerter must follow its streams and log alerts (Phase 1 Task 14).

Before 2026-11-13, `main()` built the daemon and returned at once: nothing
read Falco, the audit log, the journal, Squid or Postgres, and the alert log
stayed empty. These tests drive the loop with fake streams.
"""

import json
import threading
from pathlib import Path

from techradar.hostsec.alerter import (
    AlerterDaemon,
    main,
    run_streams,
    stream_commands,
)
from techradar.settings import Settings

FALCO_LINE = json.dumps(
    {
        "time": "2026-11-13T02:00:00.000000000Z",
        "rule": "TR shell or package manager in container",
        "priority": "Critical",
        "output": "Shell spawned",
        "output_fields": {"container.name": "techradar-bot-1"},
    }
)
AUDIT_LINE = (
    "type=SYSCALL msg=audit(1794514104.903:812): arch=c000003e syscall=257 success=yes "
    'exit=3 comm="cat" exe="/usr/bin/cat" key="tr_honey"'
)
AUDIT_PATH_LINE = 'type=PATH msg=audit(1794514104.903:812): item=0 name="secrets/aws_root_key.txt"'
SQUID_LINE = (
    "1794514104.903      0 172.20.0.3 TCP_DENIED/403 3352 "
    "CONNECT 1.1.1.1:443 - HIER_NONE/- text/html"
)


def settings(tmp_path: Path) -> Settings:
    return Settings(
        telegram_owner_chat_id=0,
        alert_log=tmp_path / "alerts.jsonl",
        secrets_dir=tmp_path / "no-secrets",  # no alerter token: log only
        incidents_dir=tmp_path / "incidents",
        evidence_pubkey=tmp_path / "evidence.pub",
    )


def logged(tmp_path: Path) -> list[dict]:
    path = tmp_path / "alerts.jsonl"
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]


def test_falco_line_is_logged(tmp_path):
    d = AlerterDaemon(settings(tmp_path))
    d.handle("falco", FALCO_LINE)
    [a] = logged(tmp_path)
    assert (a["rule"], a["level"], a["service"]) == (
        "TR shell or package manager in container",
        "critical",
        "bot",
    )


def test_raw_audit_log_line_with_honey_key_is_critical(tmp_path):
    d = AlerterDaemon(settings(tmp_path))
    d.handle("auditd", AUDIT_LINE)
    d.handle("auditd", AUDIT_PATH_LINE)  # same event, no key: no second alert
    [a] = logged(tmp_path)
    assert (a["rule"], a["level"], a["source"]) == ("tr_honey", "critical", "auditd")


def test_journal_json_line_is_parsed(tmp_path):
    d = AlerterDaemon(settings(tmp_path))
    d.handle("journal", json.dumps({"SYSLOG_IDENTIFIER": "sudo", "MESSAGE": "sudo: ls"}))
    [a] = logged(tmp_path)
    assert a["rule"] == "sudo used"


def test_squid_denial_maps_the_client_to_its_service(tmp_path):
    d = AlerterDaemon(settings(tmp_path), client_map=lambda: {"172.20.0.3": "egress-probe"})
    d.handle("squid", SQUID_LINE)
    [a] = logged(tmp_path)
    assert (a["rule"], a["level"]) == ("outbound attempt from egress-probe", "critical")


def test_a_bad_line_never_stops_the_daemon(tmp_path):
    d = AlerterDaemon(settings(tmp_path))
    d.handle("journal", "{not json")
    d.handle("falco", "garbage")
    d.handle("unknown-stream", "x")
    assert logged(tmp_path) == []


def test_run_streams_pumps_every_stream_until_stopped(tmp_path):
    d = AlerterDaemon(settings(tmp_path))
    stop = threading.Event()
    lines = {"falco": [FALCO_LINE], "auditd": [AUDIT_LINE]}

    def spawn(kind, cmd):
        yield from lines.get(kind, [])

    def on_idle():
        if len(logged(tmp_path)) >= 2:
            stop.set()

    run_streams(
        d,
        [("falco", ["x"]), ("auditd", ["y"])],
        spawn=spawn,
        stop=stop,
        on_idle=on_idle,
        restart_delay_s=0.01,
    )
    assert {a["rule"] for a in logged(tmp_path)} == {
        "TR shell or package manager in container",
        "tr_honey",
    }


def test_stream_commands_follow_the_plan_sources():
    cmds = dict(stream_commands())
    assert cmds["falco"][-1] == "/var/log/falco/events.json"
    assert cmds["auditd"][-1] == "/var/log/audit/audit.log"
    assert "-F" in cmds["falco"] and "-F" in cmds["auditd"]
    assert cmds["journal"][:2] == ["journalctl", "-f"]
    for ident in ["sudo", "systemd-logind", "aide", "techradar-integrity", "techradar-resources"]:
        assert ident in cmds["journal"]
    for svc in ["squid", "postgres"]:
        assert cmds[svc][:4] == ["docker", "compose", "logs", "-f"]
        assert "--no-log-prefix" in cmds[svc] and cmds[svc][-1] == svc
    # Start from now: old lines must not raise alerts again after a restart.
    assert "0" in cmds["falco"] and "0s" in cmds["squid"]


def test_main_runs_the_loop_instead_of_returning(monkeypatch, tmp_path):
    called = {}
    monkeypatch.setattr("techradar.hostsec.alerter.get_settings", lambda: settings(tmp_path))
    monkeypatch.setattr(
        "techradar.hostsec.alerter.run_streams",
        lambda daemon, streams, **kw: called.setdefault("streams", streams),
    )
    assert main([]) == 0
    assert {k for k, _ in called["streams"]} == {
        "falco",
        "auditd",
        "journal",
        "squid",
        "postgres",
    }


def test_client_map_comes_from_compose_without_running_docker(tmp_path):
    from techradar.hostsec.alerter import client_map_from_compose

    compose = tmp_path / "compose.yaml"
    compose.write_text(
        "services:\n"
        "  squid:\n    networks:\n      egress_internal:\n        ipv4_address: 10.250.10.2\n"
        "  egress-probe:\n    networks:\n      egress_internal:\n"
        "        ipv4_address: 10.250.10.20\n"
        "  parser:\n    network_mode: none\n"
        "  bot:\n    networks: [db]\n",
        encoding="utf-8",
    )
    assert client_map_from_compose(compose) == {
        "10.250.10.2": "squid",
        "10.250.10.20": "egress-probe",
    }


def test_client_map_is_only_consulted_for_denials(tmp_path):
    calls = []

    def cmap():
        calls.append(1)
        return {}

    d = AlerterDaemon(settings(tmp_path), client_map=cmap)
    d.handle("squid", "1794514104.903 0 10.250.10.11 TCP_MISS/200 512 GET http://ok/ - x")
    assert calls == []
