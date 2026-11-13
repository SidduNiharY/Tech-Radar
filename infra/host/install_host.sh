#!/bin/bash
# Install the TechRadar host units, audit rules and AIDE config with the
# real repo path and owner.
#
# The files in the repo name /home/techradar/TechRadarBrain, the user
# `techradar` and (for the backup) /opt/techradar. This script writes copies
# with REPO and OWNER put in, so the units can start on the real server.
#
#   sudo OWNER="$USER" bash infra/host/install_host.sh      # install and enable
#   DESTDIR=/tmp/x REPO=/srv/tr OWNER=alice bash ...        # write files only (tests)
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="${REPO:-$(cd "$HERE/../.." && pwd)}"
OWNER="${OWNER:-${SUDO_USER:-}}"
DESTDIR="${DESTDIR:-}"

if [ -z "$OWNER" ] || [ "$OWNER" = "root" ]; then
    echo "Set OWNER to the account that owns the repo (not root)." >&2
    exit 1
fi
if [ -z "$DESTDIR" ] && [ "$(id -u)" -ne 0 ]; then
    echo "Run with sudo (or set DESTDIR to write the files somewhere else)." >&2
    exit 1
fi
OWNER_HOME="/home/$OWNER"

render() { # src dest mode
    mkdir -p "$(dirname "$2")"
    sed -e "s#/home/techradar/TechRadarBrain/infra/host/aide/techradar.conf#/etc/aide/techradar.conf#g" \
        -e "s#/home/techradar/TechRadarBrain#$REPO#g" \
        -e "s#/opt/techradar#$REPO#g" \
        -e "s#/home/techradar/#$OWNER_HOME/#g" \
        -e "s#^User=techradar\$#User=$OWNER#" \
        "$1" > "$2"
    chmod "$3" "$2"
}

UNIT_DIR="$DESTDIR/etc/systemd/system"
for f in "$HERE"/alerter/*.service "$HERE"/alerter/*.timer \
         "$HERE"/timers/*.service "$HERE"/timers/*.timer \
         "$HERE"/../backup/*.service "$HERE"/../backup/*.timer; do
    render "$f" "$UNIT_DIR/$(basename "$f")" 0644
done
render "$HERE/audit/techradar.rules" "$DESTDIR/etc/audit/rules.d/techradar.rules" 0640
render "$HERE/aide/techradar.conf" "$DESTDIR/etc/aide/techradar.conf" 0600

# Falco reads rules.d in name order: the lists must load before the rules.
FALCO="$HERE/../falco"
render "$FALCO/generated_lists.yaml" "$DESTDIR/etc/falco/rules.d/10-techradar-lists.yaml" 0644
render "$FALCO/techradar_rules.yaml" "$DESTDIR/etc/falco/rules.d/20-techradar-rules.yaml" 0644
render "$FALCO/techradar-output.yaml" "$DESTDIR/etc/falco/config.d/techradar-output.yaml" 0644
render "$FALCO/logrotate" "$DESTDIR/etc/logrotate.d/falco-techradar" 0644
render "$FALCO/falco-logging.conf" \
    "$DESTDIR/etc/systemd/system/falco-modern-bpf.service.d/techradar-logging.conf" 0644

if [ -n "$DESTDIR" ]; then
    echo "Wrote files under $DESTDIR (nothing enabled)."
    exit 0
fi

install -d -m 0750 -o "$OWNER" -g "$OWNER" /var/lib/techradar-alerter
# Made as the owner: a root chown inside the owner's tree could follow a symlink.
sudo -u "$OWNER" mkdir -p "$REPO/data/incidents"
install -d -m 0700 -o root -g root /var/lib/techradar-honey
augenrules --load
# The alerter (owner, adm group) follows /var/log/falco/events.json.
install -d -m 0750 -o root -g adm /var/log/falco
if systemctl cat falco-modern-bpf.service >/dev/null 2>&1; then
    # Checks the whole configured set (our rules use Falco's default macros).
    falco --dry-run
    systemctl daemon-reload  # picks up the logging drop-in
    systemctl restart falco-modern-bpf.service
else
    echo "Falco is not installed yet (RUNBOOK section 22.3); its rules are in place for when it is."
fi
systemctl daemon-reload
for t in aide integrity resources lynis backup; do
    systemctl enable --now "techradar-$t.timer"
done
# Settings needs TR_TELEGRAM_OWNER_CHAT_ID. Before the Telegram stage there is
# no .env, and the alerter would crash on start; 0 means "no chat yet".
if [ ! -f "$REPO/.env" ]; then
    sudo -u "$OWNER" sh -c 'umask 077 && printf "%s\n" "# Set your real chat ID in the Telegram stage." "TR_TELEGRAM_OWNER_CHAT_ID=0" > "$1"' sh "$REPO/.env"
    echo "Created $REPO/.env with a placeholder chat ID (0)."
fi
# The alerter logs every alert to /var/lib/techradar-alerter/alerts.jsonl and
# only sends to Telegram when secrets/alerter_bot_token exists, so it runs
# from the start. The heartbeat only sends to Telegram: SKIP_TELEGRAM=1 (or
# the old name SKIP_ALERTER=1) leaves it off until the Telegram stage.
systemctl enable --now techradar-alerter.service
# enable --now leaves a running alerter alone; restart so updated code runs.
systemctl restart techradar-alerter.service
if [ "${SKIP_TELEGRAM:-${SKIP_ALERTER:-0}}" = "1" ]; then
    echo "Heartbeat installed but NOT enabled (SKIP_TELEGRAM=1)."
else
    systemctl enable --now techradar-heartbeat.timer
fi
echo "Installed for OWNER=$OWNER REPO=$REPO. Next: sudo aide --init --config /etc/aide/techradar.conf"
