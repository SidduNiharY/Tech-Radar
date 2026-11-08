"""Host resource watcher: GPU, restart loops, and outbound bytes."""

from __future__ import annotations

import csv
import io
import json
import logging
import re
import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from pathlib import Path

from pydantic import BaseModel

logger = logging.getLogger(__name__)

GPU_SERVICES: set[str] = {"ollama", "voice-worker", "voice-live", "evals"}
STATE_FILE = Path("/var/lib/techradar-alerter/resources.json")
_CGROUP_DOCKER_REGEX = re.compile(r"docker[-/]([0-9a-fA-F]{12,64})")


class GpuApp(BaseModel):
    """Running GPU process."""

    pid: int
    name: str
    used_mib: int


def parse_gpu_apps(csv_text: str) -> list[GpuApp]:
    """Parse nvidia-smi compute-apps CSV output."""
    apps: list[GpuApp] = []
    reader = csv.reader(io.StringIO(csv_text))
    for row in reader:
        if not row or len(row) < 3:
            continue
        try:
            pid = int(row[0].strip())
            name = row[1].strip()
            used_mib = int(row[2].strip())
            apps.append(GpuApp(pid=pid, name=name, used_mib=used_mib))
        except ValueError, IndexError:
            continue
    return apps


def service_of_pid(pid: int, cgroup_text: str, containers: Mapping[str, str]) -> str | None:
    """Resolve container ID from cgroup text, then map to compose service."""
    # Check regex match for docker container IDs
    for match in _CGROUP_DOCKER_REGEX.finditer(cgroup_text):
        cid = match.group(1).lower()
        if cid in containers:
            return containers[cid]
        if cid[:12] in containers:
            return containers[cid[:12]]
        for key, svc in containers.items():
            if cid.startswith(key.lower()) or key.lower().startswith(cid):
                return svc

    # Fallback: check if any known container ID appears anywhere in the cgroup text
    for key, svc in containers.items():
        if key.lower() in cgroup_text.lower():
            return svc

    return None


def check_gpu(apps: Sequence[GpuApp], services: Mapping[int, str | None]) -> list[str]:
    """Flag any GPU process not owned by an approved GPU service."""
    alerts: list[str] = []
    for app in apps:
        svc = services.get(app.pid)
        if svc not in GPU_SERVICES:
            alerts.append(f"CRITICAL unknown GPU process {app.name}")
    return alerts


def check_gpu_busy(
    util_last_15min: Sequence[int],
    loaded_models: Sequence[str],
    voice_running: bool,
) -> str | None:
    """Warn when GPU is continuously busy while no model is loaded and voice is idle."""
    if not util_last_15min:
        return None
    if all(u >= 80 for u in util_last_15min) and not loaded_models and not voice_running:
        return "WARNING GPU busy with no job"
    return None


def check_restarts(
    prev: Mapping[str, tuple[int, datetime]],
    now: Mapping[str, int],
    at: datetime,
) -> list[str]:
    """Warn when a service's restart count grew by 3 or more within 10 minutes."""
    alerts: list[str] = []
    for svc in sorted(now.keys()):
        if svc in prev:
            prev_count, prev_time = prev[svc]
            time_diff = at - prev_time
            if timedelta(seconds=0) <= time_diff <= timedelta(minutes=10):
                if (now[svc] - prev_count) >= 3:
                    alerts.append(f"WARNING {svc} restarting")
    return alerts


def check_outbound_bytes(
    squid_lines: Sequence[str],
    client_map: Mapping[str, str],
    limit_bytes: int = 200_000_000,
) -> list[str]:
    """Warn when a service exceeds its hourly outbound byte allowance."""
    service_bytes: dict[str, int] = {}
    for line in squid_lines:
        line = line.strip()
        if not line:
            continue
        tokens = line.split()
        if len(tokens) < 5:
            continue
        client_ip = tokens[2]
        service = client_map.get(client_ip, client_ip)
        try:
            bytes_val = int(tokens[4])
        except ValueError:
            continue
        service_bytes[service] = service_bytes.get(service, 0) + bytes_val

    alerts: list[str] = []
    for svc in sorted(service_bytes.keys()):
        total = service_bytes[svc]
        if total > limit_bytes:
            mb = total // 1_000_000
            alerts.append(f"WARNING {svc} sent {mb} MB in an hour")
    return alerts


def _load_state(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception as e:
            logger.debug("Failed to read state file %s: %s", path, e)
            return {}
    return {}


def _save_state(path: Path, state: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, default=str))
    except Exception as e:
        logger.debug("Failed to write state file %s: %s", path, e)


def main() -> int:
    """Periodic resource monitoring run."""
    state = _load_state(STATE_FILE)
    alerts: list[str] = []

    nvidia_smi = shutil.which("nvidia-smi")
    apps: list[GpuApp] = []

    # 1. GPU apps and usage
    if nvidia_smi:
        try:
            proc = subprocess.run(  # noqa: S603
                [
                    nvidia_smi,
                    "--query-compute-apps=pid,process_name,used_memory",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )
            apps = parse_gpu_apps(proc.stdout) if proc.returncode == 0 else []
        except Exception as e:
            logger.debug("Failed to query compute apps: %s", e)

    services_by_pid: dict[int, str | None] = {}
    for app in apps:
        cgroup_path = Path(f"/proc/{app.pid}/cgroup")
        cgroup_text = cgroup_path.read_text() if cgroup_path.exists() else ""
        services_by_pid[app.pid] = service_of_pid(app.pid, cgroup_text, {})

    alerts.extend(check_gpu(apps, services_by_pid))

    # 2. Check GPU busy
    util_history: list[int] = state.get("util_last_15min", [])
    if nvidia_smi:
        try:
            proc = subprocess.run(  # noqa: S603
                [nvidia_smi, "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                current_util = int(proc.stdout.strip().split("\n")[0])
                util_history.append(current_util)
                if len(util_history) > 15:
                    util_history = util_history[-15:]
        except Exception as e:
            logger.debug("Failed to query GPU utilization: %s", e)

    state["util_last_15min"] = util_history
    busy_alert = check_gpu_busy(util_history, [], voice_running=False)
    if busy_alert:
        alerts.append(busy_alert)

    # 3. Output any generated alerts
    for alert in alerts:
        sys.stdout.write(f"{alert}\n")
        sys.stdout.flush()

    _save_state(STATE_FILE, state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
