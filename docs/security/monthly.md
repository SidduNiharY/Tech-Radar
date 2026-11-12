# Monthly Security Checklist

Review and execute on the first weekend of every month. Record execution date, status, and notes.

| Checklist Item | Frequency | Verification Method | Pass Criteria | Date Checked | Status | Notes / Sign-off |
|---|---|---|---|---|---|---|
| Database Restore Test | Monthly | `bash infra/backup/restore_test.sh` | Prints `RESTORE OK (<n> tables match)` | | | |
| Read-only Host Check | Monthly | `bash infra/host/check_host.sh` | All checks `PASS` (or allowable `WARN`) | | | |
| Network Exposure (LAN) | Monthly | `nmap -Pn -p- <LAN_IP>` | No open ports | | | |
| Network Exposure (Tailscale) | Monthly | `nmap -Pn -p- <TAILSCALE_IP>` | Port 22 (Tailscale SSH) only | | | |
| Telegram Active Sessions | Monthly | Telegram App > Settings > Devices | Owner mobile device only | | | |
| Tailscale Device List | Monthly | Tailscale Admin Console | Approved personal devices only | | | |
| Syncthing Device List | Monthly | Syncthing GUI / Config | Paired only with own trusted devices | | | |
| Honeytoken Verification | Monthly | `uv run python scripts/plant_honeytokens.py --verify` | All honeytokens intact; zero audit access | | | |
| Lynis Hardening Audit | Monthly | The `techradar-lynis` timer writes `/var/log/techradar/lynis/<YYYY-MM>.txt` (root-owned); copy it in as yourself: `sudo cat /var/log/techradar/lynis/$(date +%Y-%m).txt > docs/security/lynis/$(date +%Y-%m).txt` | Hardening index recorded in `docs/security/lynis/` | | | |
| Secret & Token Rotation | Monthly | Check token ages in `secrets/` | Tokens rotated per lifecycle schedule | | | |
| Agent Skills & Plugins Audit | Monthly | Inspect installed MCPs/skills against `AGENTS.md` | Zero unvetted or unpinned tools | | | |
| Residual Risk Review | Monthly | Review `02_Tech_Stack_and_Security.md` & incident logs | All threat mitigations functioning | | | |
