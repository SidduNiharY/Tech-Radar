"""Host security alerter daemon, Telegram dispatcher, and daily heartbeat runner."""

import argparse
import json
import logging
import queue
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import yaml

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
        if client_map is None:
            static = client_map_from_compose(Path("compose.yaml"))
            client_map = lambda: static  # noqa: E731
        self._client_map = client_map
        self._migrating_flag = migrating_flag

    def handle(self, kind: str, line: str) -> None:
        """Route one line from a stream to its parser. A bad line is logged, never raised."""
        line = line.rstrip("\n")
        if not line.strip():
            return
        try:
            if kind == "falco":
                # A journal entry; Falco's own startup lines and journald's
                # byte-array messages are not events and are skipped.
                message = json.loads(line).get("MESSAGE")
                if isinstance(message, str) and message.startswith("{"):
                    self.process_falco_line(message)
            elif kind == "auditd":
                # audit.log is read directly (journald gets no audit records on
                # this host); only the SYSCALL record carries the watch key.
                if 'key="tr_' in line:
                    self.process_journal_entry({"SYSLOG_IDENTIFIER": "audit", "MESSAGE": line})
            elif kind == "journal":
                self.process_journal_entry(json.loads(line))
            elif kind == "squid":
                if "TCP_DENIED" in line:
                    self.process_squid_line(line, self._client_map())
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


def stream_commands() -> list[tuple[str, list[str]]]:
    """The streams the alerter follows (Phase 1 Task 14), each starting from now."""
    journal = ["journalctl", "-f", "-n", "0", "-o", "json"]
    for ident in JOURNAL_IDENTIFIERS:
        journal += ["-t", ident]
    logs = ["docker", "compose", "logs", "-f", "--no-color", "--no-log-prefix", "--since", "0s"]
    return [
        # Falco's JSON events, from the journal of Falco's own unit.
        (
            "falco",
            ["journalctl", "-f", "-n", "0", "-o", "json", "_SYSTEMD_UNIT=falco-modern-bpf.service"],
        ),
        ("auditd", ["tail", "-n", "0", "-F", "/var/log/audit/audit.log"]),
        ("journal", journal),
        ("squid", [*logs, "squid"]),
        ("postgres", [*logs, "postgres"]),
    ]


def client_map_from_compose(compose_path: Path) -> dict[str, str]:
    """Squid client IP -> Compose service, from the fixed egress addresses.

    Read from compose.yaml instead of asking Docker: short-lived containers
    (an egress probe) exit before a runtime lookup can see them, and no
    command runs per log line.
    """
    try:
        data = yaml.safe_load(compose_path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        logger.error("Alerter cannot read %s: %s", compose_path, exc)
        return {}
    mapping: dict[str, str] = {}
    for name, svc in (data.get("services") or {}).items():
        nets = (svc or {}).get("networks") or {}
        if isinstance(nets, dict):
            addr = (nets.get("egress_internal") or {}).get("ipv4_address")
            if addr:
                mapping[str(addr)] = str(name)
    return mapping


def popen_lines(kind: str, cmd: list[str]) -> Iterator[str]:
    """Yield the output lines of a long-running command (no shell)."""
    with subprocess.Popen(  # noqa: S603
        cmd,
        stdout=subprocess.PIPE,
        # stderr is inherited, so a stream's errors land in the journal.
        text=True,
        bufsize=1,
    ) as proc:
        if proc.stdout is None:
            return
        yield from proc.stdout


class RoundRobin:
    """Serve the per-stream queues in turn.

    Each stream has its own bounded queue, so a flood on one (the journal
    can be written by any local user) fills only that queue and blocks only
    that stream's reader; every other stream still gets a line each round.
    """

    def __init__(self, queues: Mapping[str, queue.Queue[tuple[str, str]]]) -> None:
        self._queues = list(queues.values())
        self._next = 0

    def next(self, *, timeout_s: float) -> tuple[str, str] | None:
        deadline = time.monotonic() + timeout_s
        while True:
            for _ in range(len(self._queues)):
                q = self._queues[self._next]
                self._next = (self._next + 1) % len(self._queues)
                try:
                    return q.get_nowait()
                except queue.Empty:
                    continue
            if time.monotonic() >= deadline:
                return None
            time.sleep(0.02)


def check_sources(streams: Sequence[tuple[str, list[str]]]) -> list[Alert]:
    """A critical alert for each followed log file the alerter cannot read.

    `tail -F` waits quietly for a file it cannot open, so without this an
    unreadable source would be a silent blind spot.
    """
    alerts: list[Alert] = []
    for kind, cmd in streams:
        if not cmd or cmd[0] != "tail":
            continue
        path = Path(cmd[-1])
        try:
            with path.open("rb"):
                pass
        except OSError as exc:
            alerts.append(
                Alert(
                    level=Level.CRITICAL,
                    source="alerter",
                    rule=f"alerter source unreadable: {kind}",
                    service=None,
                    summary=f"{path}: {exc.strerror or exc}"[:200],
                    at=datetime.now(UTC),
                )
            )
    return alerts


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
    # One bounded queue per stream, served in turn (see RoundRobin): a flood
    # on one stream can only block that stream's own reader.
    queues: dict[str, queue.Queue[tuple[str, str]]] = {
        kind: queue.Queue(maxsize=10_000) for kind, _ in streams
    }
    scheduler = RoundRobin(queues)

    def pump(kind: str, cmd: list[str]) -> None:
        target = queues[kind]
        while not stop.is_set():
            try:
                for line in spawn(kind, cmd):
                    target.put((kind, line))
                    if stop.is_set():
                        return
            except Exception as exc:
                logger.error("Alerter stream %s failed: %s", kind, exc)
            logger.warning("Alerter stream %s ended; restarting in %ss", kind, restart_delay_s)
            stop.wait(restart_delay_s)

    for kind, cmd in streams:
        threading.Thread(target=pump, args=(kind, cmd), name=f"alerter-{kind}", daemon=True).start()

    while not stop.is_set():
        item = scheduler.next(timeout_s=0.2)
        if item is not None:
            daemon.handle(*item)
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
    streams = stream_commands()
    for alert in check_sources(streams):
        daemon.process_alert(alert)
    run_streams(daemon, streams)
    return 0


if __name__ == "__main__":
    sys.exit(main())
