"""Automated host security containment and forensic evidence collection."""

import json
import logging
import os
import subprocess
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel

from techradar.hostsec.alerts import Alert, Level

logger = logging.getLogger(__name__)


class Runner(Protocol):
    """Protocol for executing host commands safely without a shell."""

    def __call__(
        self,
        args: list[str],
        *,
        timeout_s: int = 60,
    ) -> subprocess.CompletedProcess: ...


class Evidence(BaseModel):
    """Collected evidence directory and list of encrypted artifacts."""

    dir: Path
    files: list[str]


def collect_evidence(
    container: str,
    run: Runner,
    out_root: Path,
    pubkey: Path,
    falco_events: Sequence[str] = (),
    now: datetime | None = None,
) -> Evidence:
    """Collect container state, diffs, logs, and Falco events, encrypted with age."""
    ts = (now or datetime.now(UTC)).strftime("%Y-%m-%dT%H%M")
    evidence_dir = out_root / f"{ts}-{container}"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(evidence_dir, 0o700)
    except OSError:
        pass

    # 1. Logs
    logs_res = run(["docker", "logs", "--tail", "5000", container])
    logs_file = evidence_dir / "logs.txt"
    logs_file.write_text(logs_res.stdout or "", encoding="utf-8")

    # 2. Inspect
    inspect_res = run(["docker", "inspect", container])
    inspect_file = evidence_dir / "inspect.json"
    inspect_file.write_text(inspect_res.stdout or "", encoding="utf-8")

    # 3. Diff
    diff_res = run(["docker", "diff", container])
    diff_file = evidence_dir / "diff.txt"
    diff_text = diff_res.stdout or ""
    diff_file.write_text(diff_text, encoding="utf-8")

    # 4. Falco events
    falco_file = evidence_dir / "falco_events.jsonl"
    falco_file.write_text(
        "\n".join(falco_events) + ("\n" if falco_events else ""),
        encoding="utf-8",
    )

    # 5. Changed files via docker cp (up to 200 MB)
    if diff_text:
        for line in diff_text.splitlines():
            parts = line.strip().split(maxsplit=1)
            if len(parts) == 2 and parts[0] in ("A", "C"):
                path_in_container = parts[1]
                safe_name = "fs_" + path_in_container.lstrip("/").replace("/", "_")
                cp_target = evidence_dir / safe_name
                run(["docker", "cp", f"{container}:{path_in_container}", str(cp_target)])

    # 6. Encrypt each file with age -R <pubkey>, delete plain copy, set mode 0o400
    encrypted_files: list[str] = []
    for plain_file in sorted(evidence_dir.iterdir()):
        if plain_file.is_file() and not plain_file.name.endswith(".age"):
            age_file = plain_file.with_name(plain_file.name + ".age")
            run(["age", "-R", str(pubkey), "-o", str(age_file), str(plain_file)])
            plain_file.unlink(missing_ok=True)
            if not age_file.exists():
                age_file.touch()
            try:
                os.chmod(age_file, 0o400)
            except OSError:
                pass
            encrypted_files.append(age_file.name)

    return Evidence(dir=evidence_dir, files=sorted(encrypted_files))


def contain(container: str, run: Runner) -> list[list[str]]:
    """Disconnect the exact container from every network, then stop it."""
    commands_run: list[list[str]] = []

    inspect_cmd = ["docker", "inspect", container]
    inspect_res = run(inspect_cmd)
    commands_run.append(inspect_cmd)

    networks: list[str] = []
    if inspect_res.stdout:
        try:
            data = json.loads(inspect_res.stdout)
            if isinstance(data, list) and data:
                net_dict = data[0].get("NetworkSettings", {}).get("Networks", {})
                networks = list(net_dict.keys())
        except (json.JSONDecodeError, KeyError, TypeError, IndexError) as exc:
            logger.debug("Failed parsing networks from docker inspect: %s", exc)

    for net in networks:
        disconnect_cmd = ["docker", "network", "disconnect", net, container]
        run(disconnect_cmd)
        commands_run.append(disconnect_cmd)

    # docker stop, not `docker compose stop <service>`: a one-off run
    # container is not the service's main container.
    stop_cmd = ["docker", "stop", container]
    run(stop_cmd)
    commands_run.append(stop_cmd)

    return commands_run


def container_for(service: str, run: Runner) -> str | None:
    """The running container of a Compose service, or None."""
    res = run(["docker", "compose", "ps", "-q", service])
    ids = [x.strip() for x in (res.stdout or "").splitlines() if x.strip()]
    return ids[0] if res.returncode == 0 and ids else None


def respond(
    a: Alert,
    mode: Literal["alert-only", "on"],
    run: Runner,
    *,
    out_root: Path,
    pubkey: Path,
    falco_events: Sequence[str] = (),
    now: datetime | None = None,
) -> str:
    """Take automated containment actions if enabled, returning action summary."""
    if mode == "on" and a.level == Level.CRITICAL and (a.container or a.service):
        # Docker commands need the exact container; `service` names a group.
        target = a.container or container_for(a.service or "", run)
        if target is None:
            return "alert only (no running container)"
        collect_evidence(
            target,
            run,
            out_root,
            pubkey,
            falco_events=falco_events,
            now=now or a.at,
        )
        contain(target, run)
        return "contained after saving evidence"

    return "alert only"
