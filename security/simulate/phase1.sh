#!/bin/bash
set -euo pipefail

# TechRadar Brain: Phase 1 Security Controls Simulation
# Simulates representative attacks and verifies alert generation within 60s.

ALERT_LOG="${TR_ALERT_LOG:-/var/lib/techradar-alerter/alerts.jsonl}"

echo "=== Starting Phase 1 Security Simulation ==="

# Alerts raised before this run must not count as a pass.
SIM_START="${SIM_START:-$(date -u +%Y-%m-%dT%H:%M:%S+00:00)}"

# True once the alert log has an alert with this rule and level, raised at or
# after SIM_START. The log is compact JSON (one Alert per line), so it is
# parsed rather than grepped.
alert_seen() {
    python3 - "$ALERT_LOG" "$1" "$2" "$SIM_START" <<'PYEOF'
import json, sys
from datetime import datetime
log, rule, level, start = sys.argv[1:5]
since = datetime.fromisoformat(start)
try:
    lines = open(log, encoding="utf-8").read().splitlines()
except OSError:
    sys.exit(1)
for raw in lines:
    try:
        a = json.loads(raw)
        if a["rule"] == rule and a["level"] == level and datetime.fromisoformat(a["at"]) >= since:
            sys.exit(0)
    except (ValueError, KeyError, TypeError):
        continue
sys.exit(1)
PYEOF
}

wait_for_alert() {
    local rule="$1"
    local expected_level="${2:-critical}"
    local timeout_s="${3:-60}"
    local start_time
    start_time=$(date +%s)

    echo -n "Waiting for alert rule: '${rule}' (${expected_level})... "
    while true; do
        if alert_seen "$rule" "$expected_level"; then
            echo "PASS"
            return 0
        fi

        local now
        now=$(date +%s)
        if (( now - start_time >= timeout_s )); then
            echo "FAIL (timeout after ${timeout_s}s)"
            return 1
        fi
        sleep 2
    done
}

# 1. Shell in container
echo "--- Attack 1: Container shell execution ---"
# postgres runs from Phase 1 on (the bot waits for the Telegram stage).
docker compose exec -T postgres sh -c true 2>/dev/null || true
wait_for_alert "TR shell or package manager in container" "critical" 60 || echo "[FAIL] Attack 1"

# 2. AWS root key honeytoken read
echo "--- Attack 2: Honeytoken file read ---"
if [ -f "secrets/aws_root_key.txt" ]; then
    cat secrets/aws_root_key.txt >/dev/null 2>&1 || true
    wait_for_alert "tr_honey" "critical" 60 || echo "[FAIL] Attack 2"
fi

# 3. Failed database login for honeytoken user admin_backup
echo "--- Attack 3: Failed DB login for admin_backup ---"
# From another container over the db network: inside the postgres container,
# 127.0.0.1 is trusted without a password, so no password check would run.
docker compose run --rm --no-deps --entrypoint python migrate -c \
    "import psycopg; psycopg.connect(host='postgres', user='admin_backup', password='wrong', dbname='techradar', connect_timeout=5)" \
    >/dev/null 2>&1 || true
wait_for_alert "admin_backup login attempt" "critical" 60 || echo "[FAIL] Attack 3"

# 4. Outbound connection outside allowed peers from isolated service
echo "--- Attack 4: Unauthorized outbound network attempt ---"
docker compose run --rm --entrypoint python migrate -c "import socket; socket.create_connection(('1.1.1.1', 443), 3)" 2>/dev/null || true
wait_for_alert "TR connection outside allowed peers" "critical" 60 || echo "[FAIL] Attack 4"

# 5. Outbound probe via Squid proxy
echo "--- Attack 5: Outbound connection from egress-probe ---"
docker compose --profile test run --rm egress-probe -sS https://example.com/ 2>/dev/null || true
wait_for_alert "outbound attempt from egress-probe" "critical" 60 || echo "[FAIL] Attack 5"

# 6. AIDE filesystem integrity change
echo "--- Attack 6: Host filesystem integrity modification ---"
if command -v sudo >/dev/null 2>&1; then
    sudo touch /etc/techradar-aide-test 2>/dev/null || true
    sudo systemctl start techradar-aide.service 2>/dev/null || true
    wait_for_alert "aide integrity" "warning" 60 || echo "[WARN] Attack 6"
    sudo rm -f /etc/techradar-aide-test 2>/dev/null || true
fi

# 7. Image digest mismatch simulation
echo "--- Attack 7: Image digest mismatch detection ---"
# The alerter reads integrity results from the journal (as the timer writes them).
# The repo's .venv directly: uv would rebuild the project and need the network.
.venv/bin/python scripts/integrity_check.py --pinned-override postgres=sha256:0000000000000000000000000000000000000000000000000000000000000000 2>&1 \
    | systemd-cat -t techradar-integrity || true
wait_for_alert "postgres digest mismatch" "critical" 60 || echo "[FAIL] Attack 7"

# 8. Unknown GPU process detection
echo "--- Attack 8: Unknown GPU process detection ---"
# A process that really opens the GPU (sleep in a --gpus container never
# does, so nvidia-smi would not list it): PyTorch from the local worker image,
# with no network. The resources timer runs every minute.
if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi >/dev/null 2>&1; then
    if ! docker image inspect techradar-worker >/dev/null 2>&1; then
        echo "[SKIP] Attack 8: build the worker image first: docker compose build worker"
    else
        docker run --rm --pull never --network none --gpus all --entrypoint python techradar-worker \
            -c 'import time, torch; x = torch.zeros(1, device="cuda"); time.sleep(90)' >/dev/null 2>&1 &
        GPU_PID=$!
        wait_for_alert "unknown GPU process" "critical" 90 || echo "[FAIL] Attack 8"
        kill "$GPU_PID" 2>/dev/null || true
    fi
else
    echo "NVIDIA GPU not detected; skipping GPU simulation."
fi

echo "=== Phase 1 Security Simulation Complete ==="
