"""Tests for source parsers: Falco, Squid, Journald, and PostgreSQL/pgaudit."""

import json

from techradar.hostsec.alerts import Level
from techradar.hostsec.sources import (
    from_falco,
    from_journal,
    from_postgres,
    from_squid,
)

FALCO_SHELL_IN_PARSER = json.dumps(
    {
        "priority": "Critical",
        "rule": "Run shell in container",
        "output": "Shell spawned in parser container",
        "time": "2026-11-08T10:00:00Z",
        "output_fields": {
            "container.name": "techradar-parser-1",
        },
    }
)

AUDIT_HONEY_ENTRY = {
    "SYSLOG_IDENTIFIER": "audit",
    "MESSAGE": (
        "type=SYSCALL msg=audit(1762590000.000:1): arch=c000003e syscall=2 "
        'key="tr_honey" comm="cat"'
    ),
}

ROLE_AUDIT_LINE = (
    "2026-11-08 10:00:00 UTC [123]: [1-1] user=postgres,db=techradar LOG:  "
    "AUDIT: SESSION,1,1,ROLE,ALTER ROLE,,,"
)


def deny_line(ip: str) -> str:
    return (
        f"1762590000.123 10 {ip} TCP_DENIED/403 3982 GET http://evil.com/ - HIER_NONE/- text/html"
    )


def test_falco_critical_maps_service() -> None:
    a = from_falco(FALCO_SHELL_IN_PARSER)
    assert a is not None
    assert (a.level, a.service) == (Level.CRITICAL, "parser")
    assert a.rule == "Run shell in container"
    assert a.source == "falco"


def test_falco_warning_level() -> None:
    line = json.dumps(
        {
            "priority": "Warning",
            "rule": "Unexpected connection",
            "output_fields": {"container.name": "techradar-fetcher-1"},
        }
    )
    a = from_falco(line)
    assert a is not None
    assert (a.level, a.service) == (Level.WARNING, "fetcher")


def test_falco_invalid_or_empty() -> None:
    assert from_falco("") is None
    assert from_falco("not json") is None
    assert from_falco('{"priority": "Debug"}') is None


def test_squid_denied_fetcher_is_warning_other_is_critical() -> None:
    m = {"172.20.0.5": "fetcher", "172.20.0.9": "worker"}
    fetcher_alert = from_squid(deny_line("172.20.0.5"), m)
    assert fetcher_alert is not None
    assert fetcher_alert.level is Level.WARNING
    assert fetcher_alert.rule == "squid deny"
    assert fetcher_alert.service == "fetcher"

    worker_alert = from_squid(deny_line("172.20.0.9"), m)
    assert worker_alert is not None
    assert worker_alert.level is Level.CRITICAL
    assert worker_alert.rule == "outbound attempt from worker"
    assert worker_alert.service == "worker"


def test_squid_allowed_is_ignored() -> None:
    line = (
        "1762590000.123 10 172.20.0.5 TCP_TUNNEL/200 3982 CONNECT "
        "arxiv.org:443 - HIER_DIRECT/128.84.21.19 -"
    )
    assert from_squid(line, {"172.20.0.5": "fetcher"}) is None


def test_honeytoken_audit_is_critical() -> None:
    a = from_journal(AUDIT_HONEY_ENTRY)
    assert a is not None
    assert a.level is Level.CRITICAL
    assert a.source == "auditd"
    assert a.rule == "tr_honey"


def test_admin_backup_login_is_critical() -> None:
    line = 'FATAL:  password authentication failed for user "admin_backup"'
    a = from_postgres(line, migrating=False)
    assert a is not None
    assert a.level is Level.CRITICAL
    assert a.rule == "admin_backup login attempt"
    assert a.service == "postgres"


def test_role_change_during_migration_is_ignored() -> None:
    assert from_postgres(ROLE_AUDIT_LINE, migrating=True) is None


def test_role_change_outside_migration_is_critical() -> None:
    a = from_postgres(ROLE_AUDIT_LINE, migrating=False)
    assert a is not None
    assert a.level is Level.CRITICAL
    assert a.rule == "unauthorized role change"


def test_postgres_honeytoken_table_read() -> None:
    line = (
        "2026-11-08 10:00:00 UTC [123]: [1-1] user=app,db=techradar LOG:  "
        "AUDIT: OBJECT,1,1,READ,SELECT,TABLE,public.bank_credentials,SELECT * FROM bank_credentials"
    )
    a = from_postgres(line, migrating=False)
    assert a is not None
    assert a.level is Level.CRITICAL
    assert a.rule == "honeytoken table read"


def test_postgres_regular_failed_login() -> None:
    line = 'FATAL:  password authentication failed for user "random_user"'
    a = from_postgres(line, migrating=False)
    assert a is not None
    assert a.level is Level.WARNING
    assert a.rule == "failed login"


def test_journal_sudo_and_login() -> None:
    sudo_entry = {"SYSLOG_IDENTIFIER": "sudo", "MESSAGE": "user : TTY=pts/0 ; COMMAND=/bin/ls"}
    a = from_journal(sudo_entry)
    assert a is not None
    assert (a.level, a.rule) == (Level.WARNING, "sudo used")

    login_entry = {"SYSLOG_IDENTIFIER": "systemd-logind", "MESSAGE": "New session 1 of user test"}
    a2 = from_journal(login_entry)
    assert a2 is not None
    assert (a2.level, a2.rule) == (Level.WARNING, "login")


def test_journal_audit_keys() -> None:
    entry_sudoers = {"SYSLOG_IDENTIFIER": "audit", "MESSAGE": 'key="tr_sudoers"'}
    assert from_journal(entry_sudoers).level is Level.CRITICAL

    entry_ssh = {"SYSLOG_IDENTIFIER": "audit", "MESSAGE": 'key="tr_ssh"'}
    assert from_journal(entry_ssh).level is Level.CRITICAL

    entry_secret = {"SYSLOG_IDENTIFIER": "audit", "MESSAGE": 'key="tr_secret_change"'}
    assert from_journal(entry_secret).level is Level.WARNING


def test_journal_aide_and_integrity() -> None:
    aide_entry = {"SYSLOG_IDENTIFIER": "aide", "MESSAGE": "AIDE found differences"}
    a = from_journal(aide_entry)
    assert a is not None
    assert (a.level, a.source) == (Level.WARNING, "aide")

    int_entry = {
        "SYSLOG_IDENTIFIER": "techradar-integrity",
        "MESSAGE": "CRITICAL checksum mismatch",
    }
    a_int = from_journal(int_entry)
    assert a_int is not None
    assert (a_int.level, a_int.source) == (Level.CRITICAL, "integrity")

    res_entry = {"SYSLOG_IDENTIFIER": "techradar-resources", "MESSAGE": "WARNING memory at 92%"}
    a_res = from_journal(res_entry)
    assert a_res is not None
    assert (a_res.level, a_res.source) == (Level.WARNING, "resources")
