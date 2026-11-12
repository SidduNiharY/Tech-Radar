"""Parsers converting raw log lines and event records into structured security alerts."""

import json
import re
from collections.abc import Mapping
from datetime import UTC, datetime

from techradar.hostsec.alerts import Alert, Level

_SERVICE_REGEX = re.compile(r"^[a-z0-9-]{1,40}$")
_FALCO_CONTAINER_REGEX = re.compile(r"^techradar-([a-z0-9-]+)-\d+$")
_IPV4_REGEX = re.compile(r"\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b")


def from_falco(line: str) -> Alert | None:
    """Parse a Falco JSON event into an Alert."""
    stripped = line.strip()
    if not stripped:
        return None

    try:
        data = json.loads(stripped)
    except Exception:
        return None

    priority = str(data.get("priority", "")).capitalize()
    if priority in ("Emergency", "Alert", "Critical", "Error"):
        level = Level.CRITICAL
    elif priority in ("Warning", "Notice"):
        level = Level.WARNING
    elif priority in ("Informational", "Info"):
        level = Level.INFO
    else:
        return None

    output_fields = data.get("output_fields") or {}
    container_name = str(output_fields.get("container.name", "")).strip()

    service: str | None = None
    if container_name:
        match = _FALCO_CONTAINER_REGEX.match(container_name)
        if match:
            service = match.group(1)
        elif _SERVICE_REGEX.match(container_name) and container_name != "host":
            service = container_name

    rule = str(data.get("rule", "falco alert"))[:80]
    output = str(data.get("output", "")).strip() or rule
    summary = output[:200]

    time_str = data.get("time")
    at: datetime
    if time_str:
        try:
            at = datetime.fromisoformat(str(time_str).replace("Z", "+00:00"))
        except Exception:
            at = datetime.now(UTC)
    else:
        at = datetime.now(UTC)

    return Alert(
        level=level,
        source="falco",
        rule=rule,
        service=service,
        summary=summary,
        at=at,
    )


def from_squid(line: str, client_map: Mapping[str, str] | None = None) -> Alert | None:
    """Parse Squid proxy access log line for TCP_DENIED events."""
    if "TCP_DENIED" not in line:
        return None

    mapping = client_map or {}
    tokens = line.strip().split()

    client_ip: str | None = None
    if len(tokens) >= 3 and _IPV4_REGEX.match(tokens[2]):
        client_ip = tokens[2]
    else:
        match = _IPV4_REGEX.search(line)
        if match:
            client_ip = match.group(1)

    service: str | None = mapping.get(client_ip) if client_ip else None
    valid_service = service if service and _SERVICE_REGEX.match(service) else None

    if service == "fetcher":
        level = Level.WARNING
        rule = "squid deny"
    else:
        level = Level.CRITICAL
        target = service or client_ip or "unknown"
        rule = f"outbound attempt from {target}"[:80]

    at: datetime
    if tokens:
        try:
            at = datetime.fromtimestamp(float(tokens[0]), tz=UTC)
        except Exception:
            at = datetime.now(UTC)
    else:
        at = datetime.now(UTC)

    return Alert(
        level=level,
        source="squid",
        rule=rule,
        service=valid_service,
        summary=line.strip()[:200],
        at=at,
    )


def _finding_rule(msg: str, fallback: str) -> str:
    """The rule for a "CRITICAL <what>[: <detail>]" line: <what>, e.g.
    "postgres digest mismatch" or "unknown GPU process", so alerts say what
    happened and group by it (the detail stays in the summary)."""
    what = msg.split(" ", 1)[1] if " " in msg else ""
    what = what.split(":", 1)[0].strip()
    return what[:80] or fallback


def from_journal(entry: dict) -> Alert | None:
    """Parse a systemd journal JSON record into an Alert."""
    ident = str(entry.get("SYSLOG_IDENTIFIER", "")).strip()
    msg = str(entry.get("MESSAGE", "")).strip()

    at: datetime
    rt_ts = entry.get("__REALTIME_TIMESTAMP")
    if rt_ts:
        try:
            at = datetime.fromtimestamp(int(rt_ts) / 1_000_000, tz=UTC)
        except Exception:
            at = datetime.now(UTC)
    else:
        at = datetime.now(UTC)

    summary = msg[:200]

    if ident == "sudo":
        return Alert(
            level=Level.WARNING,
            source="journal",
            rule="sudo used",
            service=None,
            summary=summary,
            at=at,
        )

    if ident == "systemd-logind":
        if "New session" in msg:
            return Alert(
                level=Level.WARNING,
                source="journal",
                rule="login",
                service=None,
                summary=summary,
                at=at,
            )
        return None

    if ident in ("audit", "audisp-syslog") or "audit" in ident:
        if "tr_honey" in msg:
            return Alert(
                level=Level.CRITICAL,
                source="auditd",
                rule="tr_honey",
                service=None,
                summary=summary,
                at=at,
            )
        if "tr_sudoers" in msg:
            return Alert(
                level=Level.CRITICAL,
                source="auditd",
                rule="tr_sudoers",
                service=None,
                summary=summary,
                at=at,
            )
        if "tr_ssh" in msg:
            return Alert(
                level=Level.CRITICAL,
                source="auditd",
                rule="tr_ssh",
                service=None,
                summary=summary,
                at=at,
            )
        if "tr_secret_change" in msg:
            return Alert(
                level=Level.WARNING,
                source="auditd",
                rule="tr_secret_change",
                service=None,
                summary=summary,
                at=at,
            )
        return None

    if ident == "aide":
        if "found differences" in msg.lower():
            return Alert(
                level=Level.WARNING,
                source="aide",
                rule="aide integrity",
                service=None,
                summary=summary,
                at=at,
            )
        return None

    if ident in ("techradar-integrity", "techradar-resources"):
        source = "integrity" if ident == "techradar-integrity" else "resources"
        if msg.startswith("CRITICAL"):
            return Alert(
                level=Level.CRITICAL,
                source=source,
                rule=_finding_rule(msg, f"{source} check failed"),
                service=None,
                summary=summary,
                at=at,
            )
        if msg.startswith("WARNING"):
            return Alert(
                level=Level.WARNING,
                source=source,
                rule=_finding_rule(msg, f"{source} warning"),
                service=None,
                summary=summary,
                at=at,
            )
        return None

    return None


def from_postgres(line: str, *, migrating: bool = False) -> Alert | None:
    """Parse PostgreSQL / pgaudit log line into an Alert."""
    at = datetime.now(UTC)
    summary = line.strip()[:200]

    # Honeytoken table read
    if "AUDIT: OBJECT" in line and "bank_credentials" in line:
        return Alert(
            level=Level.CRITICAL,
            source="pgaudit",
            rule="honeytoken table read",
            service="postgres",
            summary=summary,
            at=at,
        )

    # Role changes
    if "AUDIT: SESSION" in line and ",ROLE," in line:
        if migrating:
            return None
        return Alert(
            level=Level.CRITICAL,
            source="pgaudit",
            rule="unauthorized role change",
            service="postgres",
            summary=summary,
            at=at,
        )

    # Admin backup failed login
    if 'password authentication failed for user "admin_backup"' in line:
        return Alert(
            level=Level.CRITICAL,
            source="pgaudit",
            rule="admin_backup login attempt",
            service="postgres",
            summary=summary,
            at=at,
        )

    # Other failed logins
    if (
        "password authentication failed for user" in line
        or "authentication failed for user" in line
    ):
        return Alert(
            level=Level.WARNING,
            source="pgaudit",
            rule="failed login",
            service="postgres",
            summary=summary,
            at=at,
        )

    return None


def from_parser(line: str) -> Alert | None:
    """Parse parser Intake log lines into structured security alerts."""
    stripped = line.strip()
    if not stripped or "INTAKE " not in stripped:
        return None

    at = datetime.now(UTC)
    summary = stripped[:200]

    if "INTAKE quarantine" in stripped:
        return Alert(
            level=Level.WARNING,
            source="parser",
            rule="intake quarantine",
            service="parser",
            summary=summary,
            at=at,
        )
    if "INTAKE reject" in stripped:
        return Alert(
            level=Level.INFO,
            source="parser",
            rule="intake reject",
            service="parser",
            summary=summary,
            at=at,
        )

    return None
