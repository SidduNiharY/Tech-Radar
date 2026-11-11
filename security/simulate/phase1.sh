#!/bin/bash
set -euo pipefail

# TechRadar Brain: Phase 1 Security Controls Simulation
# Simulates representative attacks and verifies alert generation within 60s.

ALERT_LOG="${TR_ALERT_LOG:-/var/lib/techradar-alerter/alerts.jsonl}"
CUDA_IMAGE="nvidia/cuda:12.6.3-base-ubuntu24.04@sha256:c87e78933f4c16e3272123bf2f75537306596d0fbaa395a29696a22786e5ee0e"

echo "=== Starting Phase 1 Security Simulation ==="

wait_for_alert() {
    local rule="$1"
    local expected_level="${2:-critical}"
    local timeout_s="${3:-60}"
    local start_time
    start_time=$(date +%s)

    echo -n "Waiting for alert rule: '${rule}' (${expected_level})... "
    while true; do
        if [ -f "$ALERT_LOG" ]; then
            if grep -F "\"rule\": \"$rule\"" "$ALERT_LOG" | grep -F "\"level\": \"$expected_level\"" >/dev/null 2>&1; then
                echo "PASS"
                return 0
            fi
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
docker compose exec -T bot sh -c true 2>/dev/null || true
wait_for_alert "TR shell or package manager in container" "critical" 60 || echo "[FAIL] Attack 1"

# 2. AWS root key honeytoken read
echo "--- Attack 2: Honeytoken file read ---"
if [ -f "secrets/aws_root_key.txt" ]; then
    cat secrets/aws_root_key.txt >/dev/null 2>&1 || true
    wait_for_alert "tr_honey" "critical" 60 || echo "[FAIL] Attack 2"
fi

# 3. Failed database login for honeytoken user admin_backup
echo "--- Attack 3: Failed DB login for admin_backup ---"
docker compose exec -T -e PGPASSWORD=wrong postgres psql -h 127.0.0.1 -U admin_backup techradar -c 'select 1' 2>/dev/null || true
wait_for_alert "failed login for admin_backup" "critical" 60 || echo "[FAIL] Attack 3"

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
    wait_for_alert "AIDE differences" "warning" 60 || echo "[WARN] Attack 6"
    sudo rm -f /etc/techradar-aide-test 2>/dev/null || true
fi

# 7. Image digest mismatch simulation
echo "--- Attack 7: Image digest mismatch detection ---"
uv run python scripts/integrity_check.py --pinned-override postgres=sha256:0000000000000000000000000000000000000000000000000000000000000000 2>/dev/null || true
wait_for_alert "postgres digest mismatch" "critical" 60 || echo "[FAIL] Attack 7"

# 8. Unknown GPU process detection
echo "--- Attack 8: Unknown GPU process detection ---"
if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi >/dev/null 2>&1; then
    docker run --rm --gpus all "$CUDA_IMAGE" sleep 90 >/dev/null 2>&1 &
    GPU_PID=$!
    wait_for_alert "unknown GPU process" "critical" 60 || echo "[FAIL] Attack 8"
    kill "$GPU_PID" 2>/dev/null || true
else
    echo "NVIDIA GPU not detected; skipping GPU simulation."
fi

echo "=== Phase 1 Security Simulation Complete ==="
