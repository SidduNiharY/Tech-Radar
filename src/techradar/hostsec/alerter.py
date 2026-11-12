"""Host security alerter daemon, Telegram dispatcher, and daily heartbeat runner."""

import argparse
import json
import logging
import queue
import re
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

from techradar.hostsec.alerts import (
    Alert,
    AlertLog,
    Level,
    feed_alerter,
    parse_quiet_hours,
    render_alert,
    render_heartbeat,
    should_send_now,
)
from techradar.hostsec.contain import respond
from techradar.hostsec.sources import (
    from_falco,
    from_journal,
    from_postgres,
    from_squid,
)
from techradar.settings import Settings, get_settings, read_secret

logger = logging.getLogger(__name__)


def send_telegram(
    token: str,
    chat_id: int,
    text: str,
    *,
    client: httpx.Client | None = None,
    max_retries: int = 3,
    timeout_s: float = 10.0,
) -> bool:
    """Send text message via Telegram Bot API with retries."""
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}

    def _post(c: httpx.Client) -> bool:
        for attempt in range(max_retries):
            try:
                resp = c.post(url, json=payload, timeout=timeout_s)
                if resp.status_code == 200:
                    return True
                logger.warning(
                    "Telegram API non-200 (%d): %s",
                    resp.status_code,
                    resp.text,
                )
            except Exception as exc:
                logger.warning("Telegram send attempt %d failed: %s", attempt + 1, exc)
            if attempt < max_retries - 1:
                time.sleep(1.0)
        return False

    if client is not None:
        return _post(client)

    with httpx.Client() as new_client:
        return _post(new_client)


def run_heartbeat(
    settings: Settings,
    *,
    client: httpx.Client | None = None,
) -> None:
    """Read last 24h of alerts, render heartbeat, and dispatch to Telegram."""
    log = AlertLog(settings.alert_log)
    since_t = datetime.now(UTC) - timedelta(hours=24)
    alerts = log.since(since_t)
    heartbeat_msg = render_heartbeat(alerts)

    try:
        token = read_secret("alerter_bot_token", settings.secrets_dir)
        chat_id = settings.alert_chat_id or settings.telegram_owner_chat_id
        send_telegram(token, chat_id, heartbeat_msg, client=client)
    except Exception as exc:
        logger.error("Failed to dispatch heartbeat: %s", exc)


def default_runner(
    args: list[str],
    *,
    timeout_s: int = 60,
) -> subprocess.CompletedProcess:
    """Execute host commands safely as argument list."""
    return subprocess.run(  # noqa: S603
        args,
        capture_output=True,
        text=True,
        timeout=timeout_s,
        check=False,
    )


class AlerterDaemon:
    """Host security alerter daemon orchestrating log parsing, containment, and alerts."""

    def __init__(
        self,
        settings: Settings,
        *,
        client_map: Callable[[], Mapping[str, str]] | None = None,
        migrating_flag: Path = Path("data/run/migrating"),
    ) -> None:
        self.settings = settings
        self.alert_log = AlertLog(settings.alert_log)
        self.quiet = parse_quiet_hours(settings.quiet_hours)
        self._client_map = client_map or ClientMap(default_runner)
        self._migrating_flag = migrating_flag

    def handle(self, kind: str, line: str) -> None:
        """Route one line from a stream to its parser. A bad line is logged, never raised."""
        line = line.rstrip("\n")
        if not line.strip():
            return
        try:
            if kind == "falco":
                self.process_falco_line(line)
            elif kind == "auditd":
                # audit.log is read directly (journald gets no audit records on
                # this host); only the SYSCALL record carries the watch key.
                if 'key="tr_' in line:
                    self.process_journal_entry({"SYSLOG_IDENTIFIER": "audit", "MESSAGE": line})
            elif kind == "journal":
                self.process_journal_entry(json.loads(line))
            elif kind == "squid":
                self.process_squid_line(line, self._client_map())
            elif kind == "docker":
                learn = getattr(self._client_map, "learn", None)
                if learn and line.strip():
                    learn(line.strip())
            elif kind == "postgres":
                self.process_postgres_line(line, migrating=self._migrating_flag.exists())
            else:
                logger.warning("Unknown alerter stream %r", kind)
        except Exception as exc:  # one bad line must not stop the alerter
            logger.error("Alerter could not handle a %s line: %s", kind, exc)

    def dispatch_alert(self, alert: Alert, action: str) -> None:
        """Send immediate or batched alert notification to Telegram."""
        now_local = datetime.now(UTC)
        try:
            token = read_secret("alerter_bot_token", self.settings.secrets_dir)
            chat_id = self.settings.alert_chat_id or self.settings.telegram_owner_chat_id
        except Exception as exc:
            logger.error("Alerter cannot read Telegram credentials: %s", exc)
            return

        if alert.level == Level.CRITICAL:
            msg = render_alert(alert, action)
            send_telegram(token, chat_id, msg)
            return

        if alert.level == Level.WARNING:
            if should_send_now(alert, now_local, self.quiet):
                msgs = feed_alerter([alert], action=action)
                for m in msgs:
                    send_telegram(token, chat_id, m)
            else:
                logger.info("Holding warning during quiet hours: %s", alert.rule)

    def process_alert(self, alert: Alert) -> None:
        """Handle a detected security alert: log, contain, and notify."""
        self.alert_log.append(alert)
        action = respond(
            alert,
            self.settings.containment,
            default_runner,
            out_root=self.settings.incidents_dir,
            pubkey=self.settings.evidence_pubkey,
        )
        self.dispatch_alert(alert, action)

    def process_falco_line(self, line: str) -> None:
        """Parse and process a Falco event line."""
        alert = from_falco(line)
        if alert is not None:
            self.process_alert(alert)

    def process_squid_line(
        self,
        line: str,
        client_map: Mapping[str, str] | None = None,
    ) -> None:
        """Parse and process a Squid access log line."""
        alert = from_squid(line, client_map)
        if alert is not None:
            self.process_alert(alert)

    def process_journal_entry(self, entry: dict) -> None:
        """Parse and process a systemd journal JSON record."""
        alert = from_journal(entry)
        if alert is not None:
            self.process_alert(alert)

    def process_postgres_line(self, line: str, *, migrating: bool = False) -> None:
        """Parse and process a PostgreSQL audit log line."""
        alert = from_postgres(line, migrating=migrating)
        if alert is not None:
            self.process_alert(alert)


# Journal identifiers the alerter cares about (from_journal handles each).
JOURNAL_IDENTIFIERS = (
    "sudo",
    "systemd-logind",
    "aide",
    "techradar-integrity",
    "techradar-resources",
)
_CONTAINER_NAME = re.compile(r"^techradar-([a-z0-9-]+?)(?:-run-[0-9a-f]+|-\d+)$")


def stream_commands() -> list[tuple[str, list[str]]]:
    """The streams the alerter follows (Phase 1 Task 14), each starting from now."""
    journal = ["journalctl", "-f", "-n", "0", "-o", "json"]
    for ident in JOURNAL_IDENTIFIERS:
        journal += ["-t", ident]
    logs = ["docker", "compose", "logs", "-f", "--no-color", "--no-log-prefix", "--since", "0s"]
    return [
        ("falco", ["tail", "-n", "0", "-F", "/var/log/falco/events.json"]),
        ("auditd", ["tail", "-n", "0", "-F", "/var/log/audit/audit.log"]),
        ("journal", journal),
        ("squid", [*logs, "squid"]),
        ("postgres", [*logs, "postgres"]),
        # Learn each new container's address while it is still running.
        (
            "docker",
            [
                "docker",
                "events",
                "--filter",
                "type=container",
                "--filter",
                "event=start",
                "--format",
                "{{.ID}}",
            ],
        ),
    ]


def build_client_map(run: Callable[..., subprocess.CompletedProcess]) -> dict[str, str]:
    """Map Squid client IPs to Compose services from the egress network."""
    res = run(
        [
            "docker",
            "network",
            "inspect",
            "techradar_egress_internal",
            "--format",
            "{{json .Containers}}",
        ]
    )
    if res.returncode != 0:
        return {}
    try:
        containers = json.loads(res.stdout or "{}") or {}
    except json.JSONDecodeError:
        return {}
    mapping: dict[str, str] = {}
    for info in containers.values():
        match = _CONTAINER_NAME.match(str(info.get("Name", "")))
        ip = str(info.get("IPv4Address", "")).split("/", 1)[0]
        if match and ip:
            mapping[ip] = match.group(1)
    return mapping


EGRESS_NETWORK = "techradar_egress_internal"


class ClientMap:
    """Squid client IP -> Compose service, remembered after a container exits.

    Short-lived containers (an egress probe, `docker compose run`) are often
    gone by the time their Squid denial is handled, so each container is
    learned when it starts (docker events) and kept after it stops.
    """

    def __init__(self, run: Callable[..., subprocess.CompletedProcess]) -> None:
        self._run = run
        self._known: dict[str, str] = {}

    def __call__(self) -> dict[str, str]:
        self._known.update(build_client_map(self._run))
        return dict(self._known)

    def learn(self, container_id: str) -> None:
        res = self._run(["docker", "inspect", "--format", "{{json .}}", container_id])
        if res.returncode != 0:
            return
        try:
            info = json.loads(res.stdout or "{}") or {}
        except json.JSONDecodeError:
            return
        match = _CONTAINER_NAME.match(str(info.get("Name", "")).lstrip("/"))
        net = (info.get("NetworkSettings") or {}).get("Networks", {}).get(EGRESS_NETWORK) or {}
        ip = str(net.get("IPAddress", ""))
        if match and ip:
            self._known[ip] = match.group(1)


def popen_lines(kind: str, cmd: list[str]) -> Iterator[str]:
    """Yield the output lines of a long-running command (no shell)."""
    with subprocess.Popen(  # noqa: S603
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        bufsize=1,
    ) as proc:
        if proc.stdout is None:
            return
        yield from proc.stdout


def run_streams(
    daemon: AlerterDaemon,
    streams: Sequence[tuple[str, list[str]]],
    *,
    spawn: Callable[[str, list[str]], Iterable[str]] = popen_lines,
    stop: threading.Event | None = None,
    on_idle: Callable[[], None] | None = None,
    restart_delay_s: float = 5.0,
) -> None:
    """Follow every stream in its own thread and handle lines one at a time.

    A stream that ends (a container restarted, a file not there yet) is
    started again after `restart_delay_s`.
    """
    stop = stop or threading.Event()
    lines: queue.Queue[tuple[str, str]] = queue.Queue()

    def pump(kind: str, cmd: list[str]) -> None:
        while not stop.is_set():
            try:
                for line in spawn(kind, cmd):
                    lines.put((kind, line))
                    if stop.is_set():
                        return
            except Exception as exc:
                logger.error("Alerter stream %s failed: %s", kind, exc)
            stop.wait(restart_delay_s)

    for kind, cmd in streams:
        threading.Thread(target=pump, args=(kind, cmd), name=f"alerter-{kind}", daemon=True).start()

    while not stop.is_set():
        try:
            kind, line = lines.get(timeout=0.2)
        except queue.Empty:
            if on_idle:
                on_idle()
            continue
        daemon.handle(kind, line)
        if on_idle:
            on_idle()


def main(args: Sequence[str] | None = None) -> int:
    """Entry point for the host alerter CLI."""
    parser = argparse.ArgumentParser(description="TechRadar host security alerter")
    parser.add_argument(
        "--heartbeat",
        action="store_true",
        help="Send 24-hour security heartbeat and exit",
    )
    parsed = parser.parse_args(args)

    settings = get_settings()
    if parsed.heartbeat:
        run_heartbeat(settings)
        return 0

    daemon = AlerterDaemon(settings)
    logger.info("TechRadar hostsec alerter daemon starting...")
    run_streams(daemon, stream_commands())
    return 0


if __name__ == "__main__":
    sys.exit(main())
