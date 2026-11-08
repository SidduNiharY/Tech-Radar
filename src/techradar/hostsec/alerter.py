"""Host security alerter daemon, Telegram dispatcher, and daily heartbeat runner."""

import argparse
import logging
import subprocess
import sys
import time
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta

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

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.alert_log = AlertLog(settings.alert_log)
        self.quiet = parse_quiet_hours(settings.quiet_hours)

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

    _ = AlerterDaemon(settings)
    logger.info("TechRadar hostsec alerter daemon starting...")
    return 0


if __name__ == "__main__":
    sys.exit(main())
