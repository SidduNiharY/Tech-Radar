#!/bin/bash
set -euo pipefail

# TechRadar Brain: Host Security Baseline Read-Only Check
# Verifies host hardening compliance according to infra/host/RUNBOOK.md.
# This script is strictly read-only and never modifies system state.

OWNER="${OWNER:-${USER:-$(id -un)}}"
failed=0

is_allowed_ip() {
    local ip="$1"

    # IPv4 loopback: 127.0.0.0/8
    if [[ "$ip" =~ ^127\.([0-9]{1,3})\.([0-9]{1,3})\.([0-9]{1,3})$ ]]; then
        return 0
    fi

    # IPv6 loopback: ::1
    if [[ "$ip" == "::1" ]]; then
        return 0
    fi

    # Tailscale IPv4: 100.64.0.0/10 (100.64.0.0 to 100.127.255.255)
    if [[ "$ip" =~ ^100\.([0-9]{1,3})\.([0-9]{1,3})\.([0-9]{1,3})$ ]]; then
        local second_octet="${BASH_REMATCH[1]}"
        if (( second_octet >= 64 && second_octet <= 127 )); then
            return 0
        fi
    fi

    # Tailscale IPv6: fd7a:115c:a1e0::/48
    shopt -s nocasematch
    if [[ "$ip" =~ ^fd7a:115c:a1e0: ]]; then
        shopt -u nocasematch
        return 0
    fi
    shopt -u nocasematch

    return 1
}

# The IP part of an `ss` local address: "0.0.0.0:22", "127.0.0.53%lo:53",
# "[::1]:631" or "[fd7a:...]%tailscale0:61088" (interface tag after the bracket).
listener_ip() {
    local field="$1" ip
    if [[ "$field" =~ ^\[([^]]+)\](%[^:]*)?:[0-9*]+$ ]]; then
        ip="${BASH_REMATCH[1]}"
    elif [[ "$field" =~ : ]]; then
        ip="${field%:*}"
    else
        ip="$field"
    fi
    echo "${ip%%%*}"
}

# 1. ufw active with default incoming deny
echo "=== Check 1: Firewall (ufw) ==="
if command -v ufw >/dev/null 2>&1; then
    ufw_status=$(ufw status verbose 2>&1 || true)
    if echo "$ufw_status" | grep -q "Status: active" && echo "$ufw_status" | grep -q "deny (incoming)"; then
        echo "[PASS] 1. ufw active with default incoming deny"
    else
        echo "[FAIL] 1. ufw is not active or default incoming policy is not deny"
        failed=$((failed + 1))
    fi
else
    echo "[FAIL] 1. ufw command not found"
    failed=$((failed + 1))
fi

# 2. ss -ltnH: no TCP listeners outside 127.0.0.0/8, ::1, 100.64.0.0/10, fd7a:115c:a1e0::/48
echo "=== Check 2: TCP Listeners (ss -ltnH) ==="
if ! command -v ss >/dev/null 2>&1; then
    echo "[FAIL] 2. ss command not found"
    failed=$((failed + 1))
else
    illegal_listeners=()
    ss_out=$(ss -ltnH 2>/dev/null || true)
    if [ -n "$ss_out" ]; then
        while IFS= read -r line; do
            [ -z "$line" ] && continue
            local_field=$(echo "$line" | awk '{print $4}')
            [ -z "$local_field" ] && continue

            ip=$(listener_ip "$local_field")

            if ! is_allowed_ip "$ip"; then
                illegal_listeners+=("$local_field (resolved IP: $ip)")
            fi
        done <<< "$ss_out"
    fi

    if [ ${#illegal_listeners[@]} -eq 0 ]; then
        echo "[PASS] 2. ss -ltnH: no TCP listeners outside 127.0.0.0/8, ::1, 100.64.0.0/10, fd7a:115c:a1e0::/48"
    else
        echo "[FAIL] 2. Disallowed TCP listeners detected:"
        for listener in "${illegal_listeners[@]}"; do
            echo "       - $listener"
        done
        failed=$((failed + 1))
    fi
fi

# 3. unattended-upgrades enabled
echo "=== Check 3: Automatic Updates (unattended-upgrades) ==="
auto_upgrades_ok=false
if command -v systemctl >/dev/null 2>&1; then
    if systemctl is-enabled unattended-upgrades.service >/dev/null 2>&1 || systemctl is-active unattended-upgrades.service >/dev/null 2>&1; then
        auto_upgrades_ok=true
    fi
fi
if [ "$auto_upgrades_ok" = false ] && [ -d /etc/apt/apt.conf.d ]; then
    if grep -rhs 'APT::Periodic::Unattended-Upgrade "1"' /etc/apt/apt.conf.d/ >/dev/null 2>&1; then
        auto_upgrades_ok=true
    fi
fi

if [ "$auto_upgrades_ok" = true ]; then
    echo "[PASS] 3. unattended-upgrades enabled"
else
    echo "[FAIL] 3. unattended-upgrades is not enabled"
    failed=$((failed + 1))
fi

# 4. tailscale status
echo "=== Check 4: Tailscale Status ==="
if command -v tailscale >/dev/null 2>&1; then
    if tailscale status >/dev/null 2>&1; then
        echo "[PASS] 4. tailscale status"
    else
        echo "[FAIL] 4. tailscale status failed"
        failed=$((failed + 1))
    fi
else
    echo "[FAIL] 4. tailscale command not found"
    failed=$((failed + 1))
fi

# 5. docker group members are exactly $OWNER
echo "=== Check 5: Docker Group Membership ==="
members=""
if command -v getent >/dev/null 2>&1; then
    members=$(getent group docker 2>/dev/null | awk -F: '{print $4}' || true)
elif [ -f /etc/group ]; then
    members=$(awk -F: '$1=="docker"{print $4}' /etc/group 2>/dev/null || true)
fi

clean_members=$(echo "$members" | tr -d '[:space:]')
expected_owner=$(echo "$OWNER" | tr -d '[:space:]')

if [ -n "$expected_owner" ] && [ "$clean_members" = "$expected_owner" ]; then
    echo "[PASS] 5. docker group members are exactly $OWNER"
else
    echo "[FAIL] 5. docker group members are '$clean_members', expected '$expected_owner'"
    failed=$((failed + 1))
fi

# 6. /etc/docker/daemon.json has max-size and no-new-privileges: true
echo "=== Check 6: Docker Daemon Configuration (/etc/docker/daemon.json) ==="
daemon_config="/etc/docker/daemon.json"
if [ -f "$daemon_config" ]; then
    has_max_size=false
    has_no_new_priv=false

    if command -v jq >/dev/null 2>&1; then
        if jq -e '.["log-opts"]["max-size"] != null and .["log-opts"]["max-size"] != ""' "$daemon_config" >/dev/null 2>&1; then
            has_max_size=true
        fi
        if jq -e '.["no-new-privileges"] == true' "$daemon_config" >/dev/null 2>&1; then
            has_no_new_priv=true
        fi
    else
        if grep -q '"max-size"' "$daemon_config"; then
            has_max_size=true
        fi
        if grep -Eq '"no-new-privileges"[[:space:]]*:[[:space:]]*true' "$daemon_config"; then
            has_no_new_priv=true
        fi
    fi

    if [ "$has_max_size" = true ] && [ "$has_no_new_priv" = true ]; then
        echo "[PASS] 6. /etc/docker/daemon.json has max-size and no-new-privileges: true"
    else
        echo "[FAIL] 6. /etc/docker/daemon.json missing required settings (max-size: $has_max_size, no-new-privileges: $has_no_new_priv)"
        failed=$((failed + 1))
    fi
else
    echo "[FAIL] 6. /etc/docker/daemon.json does not exist"
    failed=$((failed + 1))
fi

# 7. AppArmor enabled (aa-status --enabled)
echo "=== Check 7: AppArmor Status ==="
if command -v aa-status >/dev/null 2>&1 && aa-status --enabled >/dev/null 2>&1; then
    echo "[PASS] 7. AppArmor enabled (aa-status --enabled)"
else
    echo "[FAIL] 7. AppArmor is not enabled"
    failed=$((failed + 1))
fi

# 8. lsblk has crypt device (LUKS)
echo "=== Check 8: Full Disk Encryption (LUKS) ==="
has_crypt=false
if command -v lsblk >/dev/null 2>&1; then
    if lsblk -o TYPE 2>/dev/null | grep -qw "crypt"; then
        has_crypt=true
    elif lsblk 2>/dev/null | grep -qw "crypt"; then
        has_crypt=true
    fi
fi

if [ "$has_crypt" = true ]; then
    echo "[PASS] 8. lsblk has crypt device (LUKS)"
else
    echo "[FAIL] 8. lsblk has no crypt device (LUKS not detected)"
    failed=$((failed + 1))
fi

# 9. Secure Boot state: PASS if enabled, WARN otherwise
echo "=== Check 9: Secure Boot State ==="
sb_enabled=false
sb_detail=""
if command -v mokutil >/dev/null 2>&1; then
    sb_detail=$(mokutil --sb-state 2>&1 || true)
    if echo "$sb_detail" | grep -qi "SecureBoot enabled"; then
        sb_enabled=true
    fi
fi

if [ "$sb_enabled" = true ]; then
    echo "[PASS] 9. Secure Boot state: enabled"
else
    echo "[WARN] 9. Secure Boot state: not enabled ($sb_detail)"
fi

# 10. timedatectl shows Asia/Kolkata
echo "=== Check 10: Timezone (Asia/Kolkata) ==="
tz_ok=false
tz_detail=""
if command -v timedatectl >/dev/null 2>&1; then
    tz_detail=$(timedatectl 2>&1 || true)
    if echo "$tz_detail" | grep -q "Asia/Kolkata"; then
        tz_ok=true
    fi
elif [ -f /etc/timezone ]; then
    tz_detail=$(cat /etc/timezone 2>/dev/null || true)
    if echo "$tz_detail" | grep -q "Asia/Kolkata"; then
        tz_ok=true
    fi
fi

if [ "$tz_ok" = true ]; then
    echo "[PASS] 10. timedatectl shows Asia/Kolkata"
else
    echo "[FAIL] 10. Timezone is not Asia/Kolkata ($tz_detail)"
    failed=$((failed + 1))
fi

# 11. techradar-backup.timer is active/installed
echo "=== Check 11: Automated Backup Timer ==="
backup_timer_ok=false
if command -v systemctl >/dev/null 2>&1; then
    if systemctl is-active techradar-backup.timer >/dev/null 2>&1; then
        backup_timer_ok=true
    elif systemctl is-enabled techradar-backup.timer >/dev/null 2>&1; then
        backup_timer_ok=true
    fi
fi
if [ "$backup_timer_ok" = false ]; then
    if [ -f /etc/systemd/system/techradar-backup.timer ] || [ -f /etc/systemd/system/timers.target.wants/techradar-backup.timer ]; then
        backup_timer_ok=true
    fi
fi

if [ "$backup_timer_ok" = true ]; then
    echo "[PASS] 11. techradar-backup.timer is active/installed"
else
    echo "[FAIL] 11. techradar-backup.timer is not active or installed"
    failed=$((failed + 1))
fi

# 12. nvidia-smi succeeds (or WARN if non-NVIDIA dev machine)
echo "=== Check 12: NVIDIA GPU Availability ==="
gpu_ok=false
if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi >/dev/null 2>&1; then
    gpu_ok=true
fi

if [ "$gpu_ok" = true ]; then
    echo "[PASS] 12. nvidia-smi succeeds"
else
    echo "[WARN] 12. nvidia-smi failed or not found (non-NVIDIA dev machine)"
fi

# 13. systemctl get-default is multi-user.target
echo "=== Check 13: Boot Target (Text Mode) ==="
if command -v systemctl >/dev/null 2>&1; then
    target=$(systemctl get-default 2>/dev/null || true)
    if [ "$target" = "multi-user.target" ]; then
        echo "[PASS] 13. systemctl get-default is multi-user.target"
    else
        echo "[FAIL] 13. systemctl get-default is '$target', expected 'multi-user.target'"
        failed=$((failed + 1))
    fi
else
    echo "[WARN] 13. systemctl not found (cannot check default target)"
fi

# 14. No browser package installed (WARN otherwise)
echo "=== Check 14: Desktop Browser Absence ==="
browser_found=false
if command -v dpkg >/dev/null 2>&1; then
    installed_browsers=$(dpkg -l 'firefox*' 'chromium*' 'google-chrome*' 2>/dev/null | grep '^ii' || true)
    if [ -n "$installed_browsers" ]; then
        browser_found=true
    fi
fi

if [ "$browser_found" = false ]; then
    echo "[PASS] 14. No desktop browsers installed"
else
    echo "[WARN] 14. Desktop browser packages detected on host"
fi

# 15. tailscale lock status reports lock enabled
echo "=== Check 15: Tailnet Lock Status ==="
if command -v tailscale >/dev/null 2>&1; then
    lock_status=$(tailscale lock status 2>&1 || true)
    if echo "$lock_status" | grep -qi "enabled"; then
        echo "[PASS] 15. tailscale lock status reports lock enabled"
    else
        echo "[WARN] 15. tailscale lock status not enabled or not configured ($lock_status)"
    fi
else
    echo "[WARN] 15. tailscale command not found (cannot check tailscale lock status)"
fi

# 16. auditd, falco-modern-bpf and techradar-alerter are active
echo "=== Check 16: Host Security Daemons (auditd, falco, alerter) ==="
daemons_ok=true
for daemon in auditd falco-modern-bpf techradar-alerter; do
    if command -v systemctl >/dev/null 2>&1; then
        # Only a running daemon counts; an installed unit file is not a monitor.
        if ! systemctl is-active "$daemon" >/dev/null 2>&1; then
            echo "[FAIL] 16. Host security daemon '${daemon}' is not active"
            daemons_ok=false
            failed=$((failed + 1))
        fi
    fi
done
if [ "$daemons_ok" = true ]; then
    echo "[PASS] 16. auditd, falco-modern-bpf and techradar-alerter are active"
fi

# 17. Systemd timers: techradar-aide, techradar-integrity, techradar-resources, techradar-heartbeat, techradar-lynis
echo "=== Check 17: Security Monitoring Systemd Timers ==="
timers_ok=true
for timer_unit in techradar-aide.timer techradar-integrity.timer techradar-resources.timer techradar-heartbeat.timer techradar-lynis.timer; do
    if command -v systemctl >/dev/null 2>&1; then
        # Only an active timer counts; a unit file on disk or in the repo does not.
        if ! systemctl is-active "$timer_unit" >/dev/null 2>&1; then
            echo "[FAIL] 17. Security timer '${timer_unit}' is not active"
            timers_ok=false
            failed=$((failed + 1))
        fi
    fi
done
if [ "$timers_ok" = true ]; then
    echo "[PASS] 17. Security timers (aide, integrity, resources, heartbeat, lynis) are active"
fi

echo ""
if [ "$failed" -eq 0 ]; then
    echo "Host check completed successfully: all required baseline checks passed."
    exit 0
else
    echo "Host check failed with $failed security baseline failure(s)."
    exit 1
fi
