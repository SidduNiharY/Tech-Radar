# TechRadar Brain: Host Setup and Hardening Runbook

This runbook provides comprehensive operator documentation for configuring, hardening, and verifying a dedicated Ubuntu LTS host running TechRadar Brain.

---

## Architecture and Security Baseline

The host architecture follows strict defense-in-depth principles:
- **Local-first execution:** Core services, databases, and AI models execute on bare-metal hardware.
- **Zero public listeners:** No open TCP or UDP ports are exposed to the local network or public internet (SEC-02, SEC-04).
- **Tailnet-only remote management:** Remote administration is conducted solely across an encrypted Tailscale mesh (SEC-03).
- **Hardened runtime:** Minimal privileges, read-only containers, AppArmor confinement, and strict log rotation (SEC-07).

---

## Table of Contents

1. [Timezone Configuration](#1-timezone-configuration)
2. [Automatic Updates (unattended-upgrades)](#2-automatic-updates-unattended-upgrades)
3. [Firewall Configuration (ufw)](#3-firewall-configuration-ufw)
4. [Tailscale Mesh Network Setup](#4-tailscale-mesh-network-setup)
5. [SSH Hardening](#5-ssh-hardening)
6. [Docker Daemon Hardening](#6-docker-daemon-hardening)
7. [GPU Drivers and Container Toolkit](#7-gpu-drivers-and-container-toolkit)
8. [Battery Charging Limit (asusctl)](#8-battery-charging-limit-asusctl)
9. [Lid Switch and Power Management](#9-lid-switch-and-power-management)
10. [Docker Group Membership](#10-docker-group-membership)
11. [Full Disk Encryption, Secure Boot, and AppArmor](#11-full-disk-encryption-secure-boot-and-apparmor)
12. [Router and Local Network Security](#12-router-and-local-network-security)
13. [Dual Boot and Disaster Recovery USB](#13-dual-boot-and-disaster-recovery-usb)
14. [Automated Verification (check_host.sh)](#14-automated-verification-check_hostsh)

---

## 1. Timezone Configuration

Consistent timestamps across logs, audits, PostgreSQL audit trails, and backups are required. The system timezone must be set to `Asia/Kolkata`.

### Setup Commands
```bash
sudo timedatectl set-timezone Asia/Kolkata
sudo systemctl restart systemd-timesyncd
```

### Verification
```bash
timedatectl status
```

**Expected Output:**
```text
               Local time: Sun 2026-11-08 17:00:00 IST
           Universal time: Sun 2026-11-08 11:30:00 UTC
                 RTC time: Sun 2026-11-08 11:30:00
                Time zone: Asia/Kolkata (IST, +0530)
System clock synchronized: yes
              NTP service: active
          RTC in local TZ: no
```

---

## 2. Automatic Updates (unattended-upgrades)

Security patches for base OS packages and kernel must be installed automatically without manual intervention.

### Setup Commands
```bash
sudo apt update && sudo apt install -y unattended-upgrades update-notifier-common

# Enable periodic updates in /etc/apt/apt.conf.d/20auto-upgrades
sudo tee /etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::Download-Upgradeable-Packages "1";
APT::Periodic::AutocleanInterval "7";
EOF

# Ensure security origins are enabled in /etc/apt/apt.conf.d/50unattended-upgrades
sudo systemctl enable --now unattended-upgrades
```

### Verification
```bash
systemctl is-active unattended-upgrades
sudo unattended-upgrade --dry-run --debug
```

---

## 3. Firewall Configuration (ufw)

The host rejects all unsolicited incoming connections on physical and wireless network interfaces. Outgoing egress is permitted (controlled inside containers via Squid proxy).

### Setup Commands
```bash
# Reset rules to default baseline
sudo ufw default deny incoming
sudo ufw default allow outgoing

# Enable the firewall
sudo ufw --force enable
```

### Verification
```bash
sudo ufw status verbose
```

**Expected Output:**
```text
Status: active
Logging: on (low)
Default: deny (incoming), allow (outgoing), disabled (routed)
New profiles: skip
```

---

## 4. Tailscale Mesh Network Setup

All ingress to the host occurs over Tailscale WireGuard mesh network. Direct LAN and WAN ingress is blocked.

### Setup Commands
```bash
# 1. Install Tailscale
curl -fsSL https://tailscale.com/install.sh | sh

# 2. Authenticate and enable Tailscale SSH
sudo tailscale up --ssh --accept-routes=false

# 3. In the Tailscale Admin Console (https://login.tailscale.com/admin/machines):
#    - Device Approval: Enable "Device authorization" so new nodes require admin sign-off.
#    - Key Expiry: Ensure key expiry is ENABLED.
#    - Tailscale Funnel: Ensure Tailscale Funnel is DISABLED (no public ingress).
#    - ACLs: Restrict SSH and service access strictly to the owner's tagged devices.
```

### Verification
```bash
tailscale status
tailscale ip -4
```

---

## 5. SSH Hardening

SSH is never exposed on physical LAN (`0.0.0.0` or `eth0`/`wlan0`). Access is either handled entirely by Tailscale SSH or bound explicitly to the Tailscale IPv4 address.

### Preferred Option: Tailscale SSH (Disable OpenSSH Daemon)
If `tailscale up --ssh` is used, the legacy OpenSSH daemon can be disabled:
```bash
sudo systemctl disable --now ssh.service
```

### Alternative Option: Bind OpenSSH Exclusively to Tailscale
If OpenSSH is required, configure `/etc/ssh/sshd_config.d/10-tailscale.conf`:
```ini
# Replace 100.x.y.z with your host's Tailscale IPv4 address
ListenAddress 100.x.y.z
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
PubkeyAuthentication yes
X11Forwarding no
MaxAuthTries 3
```

Restart SSH:
```bash
sudo systemctl restart ssh
```

### Verification
Verify with `ss -ltnH` that no SSH port listens on `0.0.0.0` or `*`:
```bash
ss -ltnH | grep :22
```

---

## 6. Docker Daemon Hardening

The Docker daemon must enforce log rotation to prevent disk exhaustion and prevent container processes from gaining additional privileges.

### Setup Commands
Create or edit `/etc/docker/daemon.json`:
```json
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  },
  "live-restore": true,
  "no-new-privileges": true
}
```

Restart Docker daemon:
```bash
sudo systemctl restart docker
```

### Verification
```bash
docker info --format 'Logging Driver: {{.LoggingDriver}}'
sudo jq . /etc/docker/daemon.json
```

---

## 7. GPU Drivers and Container Toolkit

Local model inference (Ollama, Whisper, Piper) requires NVIDIA GPU acceleration and container access.

### Setup Commands
```bash
# 1. Install recommended NVIDIA proprietary driver
sudo ubuntu-drivers autoinstall

# 2. Install NVIDIA Container Toolkit
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

sudo apt update
sudo apt install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

### Verification
```bash
nvidia-smi
docker run --rm --gpus all ubuntu:24.04 nvidia-smi
```

---

## 8. Battery Charging Limit (asusctl)

When running on an ASUS gaming laptop (e.g., ROG Zephyrus / TUF) operating as an always-on 24/7 server, cap the battery charge limit to 80% to prevent Li-ion cell degradation.

### Setup Commands
```bash
# Using ASUS Linux control utility
asusctl -c 80
```

### Kernel Sysfs Fallback (for generic hardware)
If `asusctl` is not applicable, set the charge threshold in sysfs:
```bash
echo 80 | sudo tee /sys/class/power_supply/BAT0/charge_control_end_threshold
```
Persist via `/etc/tmpfiles.d/battery-charge-limit.conf`:
```text
w /sys/class/power_supply/BAT0/charge_control_end_threshold - - - - 80
```

### Verification
```bash
asusctl -c status || cat /sys/class/power_supply/BAT*/charge_control_end_threshold
```

---

## 9. Lid Switch and Power Management

The host operates in clamshell mode (closed lid) as a headless server. Systemd must be configured to ignore lid switch events so the system remains running on AC power.

### Setup Commands
Edit `/etc/systemd/logind.conf` (or drop in `/etc/systemd/logind.conf.d/lid.conf`):
```ini
[Login]
HandleLidSwitch=ignore
HandleLidSwitchExternalPower=ignore
HandleLidSwitchDocked=ignore
LidSwitchIgnoreInhibited=no
```

Apply changes:
```bash
sudo systemctl restart systemd-logind
```

### Verification
```bash
systemd-analyze cat-config systemd/logind.conf | grep -E "HandleLidSwitch"
```

---

## 10. Docker Group Membership

To prevent local privilege escalation, the `docker` group membership must be restricted strictly to the primary administrative user (`$OWNER`). No guest, service, or shared accounts may exist in this group.

### Setup Commands
```bash
# Add only the owner
sudo usermod -aG docker "$OWNER"
```

### Verification
```bash
# Must output exactly: docker:x:<gid>:<owner>
getent group docker
```

---

## 11. Full Disk Encryption, Secure Boot, and AppArmor

Protect against offline physical theft and unauthorized firmware/bootloader tampering:
1. **Full Disk Encryption (LUKS):** Configured at OS installation time. All data partitions reside within encrypted dm-crypt volumes.
2. **Secure Boot:** Enabled in UEFI firmware to verify kernel and module signatures.
3. **AppArmor:** Enforces mandatory access control on host binaries and Docker containers.

### Verification Commands
```bash
# Check LUKS encrypted volumes
lsblk -o NAME,TYPE,FSTYPE,MOUNTPOINTS | grep crypt

# Check Secure Boot state
mokutil --sb-state

# Check AppArmor state
sudo aa-status --enabled && sudo aa-status
```

---

## 12. Router and Local Network Security

The host environment relies on physical and network boundaries:
1. **UPnP (Universal Plug and Play):** Must be DISABLED on the local Wi-Fi router / gateway to prevent automated port forwarding.
2. **Port Forwarding:** Zero inbound port forwarding rules configured on the router.
3. **LAN Isolation:** If supported, place the host on an isolated IoT / server VLAN with client isolation enabled.

### Verification
From an external network or mobile phone disconnected from Wi-Fi:
```bash
# Ensure no open WAN ports point to your public IP
nmap -Pn -p- <your-public-ip>
```

---

## 13. Dual Boot and Disaster Recovery USB

For dual-boot installations (Windows / Ubuntu):
1. **Default Boot Entry:** Ubuntu must be set as the default entry in GRUB (`GRUB_DEFAULT=0`).
2. **Windows Configuration:** BitLocker must be enabled on Windows partitions. Disable "Fast Startup" in Windows Control Panel to avoid ext4 filesystem corruption.
3. **Recovery USB:** Keep a bootable Ubuntu 24.04 LTS USB drive available offline with LUKS header backups and recovery scripts.

---

## 14. Passkeys and Hardware Multi-Factor Authentication

1. **GitHub & Tailscale Auth:** Protect GitHub and primary Identity Provider (IdP) with FIDO2 / WebAuthn passkeys (or hardware security keys like YubiKey).
2. **Fallback:** Use TOTP authenticator apps (e.g., Aegis, Ente, 1Password) rather than SMS/voice verification.
3. **Recovery Codes:** Store offline printed recovery codes in a secure physical location.

---

## 15. Telegram Account Hardening

1. **Two-Step Verification:** Enable Telegram Cloud Password (2FA) with an offline recovery passphrase.
2. **Active Sessions:** Regularly terminate stale web or mobile sessions in Telegram Settings > Devices.

---

## 16. Tailnet Lock

Enforce Tailscale network cryptographic authorization:
```bash
# Initialize Tailnet Lock with trusted signing keys (Mac and phone)
tailscale lock init

# On new devices, sign the node key from a trusted device:
tailscale lock sign <node-key>
```
Verify status:
```bash
tailscale lock status
```

---

## 17. Text-Mode Boot and Browser Removal

Prevent accidental GUI browsing or browser exploit surface on the host:
```bash
# Set system default boot target to non-graphical multi-user mode
sudo systemctl set-default multi-user.target

# Remove desktop browsers
sudo apt-get purge -y firefox* chromium* google-chrome*
```

---

## 18. Firmware and BIOS/UEFI Security

1. **Supervisor Password:** Set an administrative BIOS/UEFI password to prevent unauthorized boot device modifications.
2. **Boot Order:** Lock boot device priority to internal encrypted NVMe drive. Disable USB / network booting unless authorized.

---

## 19. Monthly Security Review

Execute the monthly maintenance checklist documented in `docs/security/monthly.md`:
```bash
# Perform monthly check sequence
bash infra/backup/restore_test.sh
bash infra/host/check_host.sh
uv run python scripts/plant_honeytokens.py --verify
```

---

## 20. Automated Verification (check_host.sh)

The `infra/host/check_host.sh` script automates verification of all security requirements. It is strictly read-only and exits 0 only when all baseline checks pass.

Run the verification:
```bash
sudo OWNER="$USER" bash infra/host/check_host.sh
```
