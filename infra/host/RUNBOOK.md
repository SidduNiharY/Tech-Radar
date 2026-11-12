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

## First Boot Order

Do the steps in this order on a fresh server (it matches Part A of `TODO_TUF_AND_MAC.md`):

1. Install Ubuntu LTS (section 11: encryption, Secure Boot, AppArmor). On the TUF, disk encryption was skipped by the owner on 2026-11-11 (accepted risk); `check_host.sh` will report it as FAIL.
2. Base hardening: timezone (1), automatic updates (2), firewall (3), Tailscale and SSH (4, 5).
3. Install the host tools (22): Docker first, then the security tools.
4. Docker daemon config (6), GPU driver and toolkit (7), battery (8), lid (9), docker group (10).
5. Accounts and network lock: router (12), passkeys (14), Telegram (15), Tailnet Lock (16), text-mode boot (17), firmware (18).
6. Clone the repo, create `secrets/` (owner only), then install the TechRadar host units (23).
7. Verify: `sudo OWNER="$USER" bash infra/host/check_host.sh` (20), then the monthly review (19).

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
14. [Passkeys and Hardware Multi-Factor Authentication](#14-passkeys-and-hardware-multi-factor-authentication)
15. [Telegram Account Hardening](#15-telegram-account-hardening)
16. [Tailnet Lock](#16-tailnet-lock)
17. [Text-Mode Boot and Browser Removal](#17-text-mode-boot-and-browser-removal)
18. [Firmware and BIOS/UEFI Security](#18-firmware-and-biosuefi-security)
19. [Monthly Security Review](#19-monthly-security-review)
20. [Automated Verification (check_host.sh)](#20-automated-verification-check_hostsh)
21. [Private Vault Sync (Syncthing)](#21-private-vault-sync-syncthing)
22. [Install the Host Tools](#22-install-the-host-tools)
23. [Install the TechRadar Host Units](#23-install-the-techradar-host-units)

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
Install Docker Engine first (section 22, step 1). Then create or edit `/etc/docker/daemon.json`:
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

`asusctl` has no package in the Ubuntu archive (the asus-linux project builds it for Fedora and Arch). On Ubuntu, use the kernel sysfs setting below, which the `asus-wmi` driver provides on the TUF. It is what the TUF uses (verified 2026-11-12: threshold 80).

### Kernel Sysfs (the TUF's method on Ubuntu)
The battery name differs between models: the TUF A15 exposes `BAT1`, not `BAT0`. Find it first:
```bash
ls /sys/class/power_supply/          # e.g. ACAD  BAT1
BAT=BAT1
echo 80 | sudo tee /sys/class/power_supply/$BAT/charge_control_end_threshold
```
Persist via `/etc/tmpfiles.d/battery-charge-limit.conf` (use your battery name):
```text
w /sys/class/power_supply/BAT1/charge_control_end_threshold - - - - 80
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

---

## 21. Private Vault Sync (Syncthing)

Obsidian vault syncing between the TUF server and the macOS client occurs strictly peer-to-peer over encrypted Tailscale without public relays or discovery servers.

### Configuration
1. Install Syncthing on both host and Mac.
2. Web GUI bound strictly to `127.0.0.1:8384` protected with administrative password.
3. Sync protocol listen address bound exclusively to `tcp://<server-tailscale-ip>:22000`.
4. Disable global discovery, local discovery (broadcasts), relays, and UPnP / NAT traversal.
5. Explicitly configure device address to the partner's Tailscale IPv4/IPv6 address.
6. Share `data/vault` to the Mac Obsidian folder.
7. Add `.stignore` in `data/vault/`:
   ```text
   .obsidian/workspace*
   passwords.md
   ```
8. Set the Obsidian Web Clipper destination to `Clippings/`.

---

## 22. Install the Host Tools

Install each tool from the Ubuntu archive or the vendor's signed apt repository, and check each signing key's fingerprint before trusting it. Versions below are the ones verified on the TUF (Ubuntu 26.04 "resolute") on 2026-11-12.

### 1. Docker Engine, Compose and Buildx (Docker's apt repository)
```bash
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /tmp/docker.asc
gpg --show-keys --with-fingerprint /tmp/docker.asc
# Must show: 9DC8 5822 9FC7 DD38 854A  E2D8 8D81 803C 0EBF CD88
sudo install -m 0644 /tmp/docker.asc /etc/apt/keyrings/docker.asc
echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
docker version --format '{{.Server.Version}}'   # TUF: 29.9.3
docker compose version                          # TUF: v5.7.1
```

### 2. Security and backup tools (Ubuntu archive)
```bash
sudo apt install -y make jq auditd aide lynis restic age shellcheck
dpkg -l auditd aide lynis restic age shellcheck | awk '/^ii/{print $2, $3}'
# TUF: auditd 1:4.1.2, aide 0.19.2, lynis 3.1.6, restic 0.18.1, age 1.2.1, shellcheck 0.11.0
```
Do not run `aideinit` (it builds a database for the stock config); section 23 initialises AIDE with the TechRadar config.

### 3. Falco (falcosecurity apt repository, exact version, `modern_ebpf`)
```bash
curl -fsSL https://falco.org/repo/falcosecurity-packages.asc -o /tmp/falco.asc
gpg --show-keys --with-fingerprint /tmp/falco.asc
# Must show: 478B 2FBB C75F 4237 B731  DA43 6510 6822 B35B 1B1F
sudo gpg --dearmor -o /usr/share/keyrings/falco-archive-keyring.gpg /tmp/falco.asc
echo "deb [signed-by=/usr/share/keyrings/falco-archive-keyring.gpg] https://download.falco.org/packages/deb stable main" \
  | sudo tee /etc/apt/sources.list.d/falcosecurity.list
sudo apt update
# 0.45.2 is the newest release before the exclude-newer cut-off (2026-11-07).
sudo FALCO_FRONTEND=noninteractive FALCO_DRIVER_CHOICE=modern_ebpf apt install -y falco=0.45.2
sudo apt-mark hold falco
sudo systemctl enable --now falco-modern-bpf.service
```
Verification: `systemctl is-active falco-modern-bpf` prints `active`; `falco --version` prints 0.45.2.
The TechRadar rules, the JSON output to `/var/log/falco/events.json` and its log rotation are installed by `install_host.sh` (section 23), which checks them with `falco --dry-run`. They match containers named `techradar-<service>-1`, which `name: techradar` in `compose.yaml` guarantees.

### 4. Syncthing (Ubuntu archive)
```bash
sudo apt install -y syncthing      # TUF candidate: 1.29.5
sudo loginctl enable-linger "$USER"   # keeps the user service running without a login
systemctl --user enable --now syncthing.service
```
Then follow section 21 (GUI on 127.0.0.1 only, Tailscale addresses only, no discovery, relays or UPnP).

### 5. Scanners for `make security` (no sudo)
```bash
bash scripts/install_security_tools.sh   # gitleaks, trivy, osv-scanner, hadolint into ~/.local/bin, SHA-256 checked
```
Semgrep runs through `uv tool run --from semgrep==1.184.0`, so it needs no install.

---

## 23. Install the TechRadar Host Units

The unit files in `infra/host/` and `infra/backup/` name `/home/techradar/TechRadarBrain` and the user `techradar`. `install_host.sh` installs copies with the real repo path and owner, loads the audit rules and enables the alerter and the timers.

The backup runs as the owner (not root), so the restic repository (default `/mnt/backup/restic`) must be writable by the owner. Root units (AIDE, Lynis) never run or write inside the repo.

Before running it: the repo is cloned, `uv sync --frozen` has built `.venv`, and `secrets/` exists (mode 700, files 600). The alerter and heartbeat need `secrets/alerter_bot_token` and the owner's chat ID.

```bash
cd ~/TechRadarBrain
sudo OWNER="$USER" bash infra/host/install_host.sh
# Before Telegram is set up (no alerter token yet), leave the alerter off:
#   sudo OWNER="$USER" SKIP_ALERTER=1 bash infra/host/install_host.sh
sudo aide --init --config /etc/aide/techradar.conf
sudo mv /var/lib/aide/techradar.db.new /var/lib/aide/techradar.db
uv run python scripts/plant_honeytokens.py --files     # decoy files; --db later, once the database secrets exist
uv run python scripts/plant_honeytokens.py --verify
```

### Verification
```bash
sudo auditctl -l | grep -c tr_                         # the TechRadar watches are loaded
systemctl is-active techradar-alerter                  # active
systemctl list-timers 'techradar-*' --no-pager         # aide, integrity, resources, heartbeat, lynis, backup
sudo OWNER="$USER" bash infra/host/check_host.sh
```
