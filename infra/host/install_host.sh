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

if [ -n "$DESTDIR" ]; then
    echo "Wrote files under $DESTDIR (nothing enabled)."
    exit 0
fi

install -d -m 0750 -o "$OWNER" -g "$OWNER" /var/lib/techradar-alerter
# Made as the owner: a root chown inside the owner's tree could follow a symlink.
sudo -u "$OWNER" mkdir -p "$REPO/data/incidents"
install -d -m 0700 -o root -g root /var/lib/techradar-honey
augenrules --load
systemctl daemon-reload
for t in aide integrity resources lynis backup; do
    systemctl enable --now "techradar-$t.timer"
done
# The alerter and heartbeat send to Telegram: they need secrets/alerter_bot_token,
# the chat ID in .env, and the internet. SKIP_ALERTER=1 leaves them installed
# but off until then; run this script again without it to turn them on.
if [ "${SKIP_ALERTER:-0}" = "1" ]; then
    echo "Alerter and heartbeat installed but NOT enabled (SKIP_ALERTER=1)."
else
    systemctl enable --now techradar-alerter.service techradar-heartbeat.timer
fi
echo "Installed for OWNER=$OWNER REPO=$REPO. Next: sudo aide --init --config /etc/aide/techradar.conf"
