#!/usr/bin/env python3
"""Check container filesystem and image digest integrity for running services."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml

from techradar.hostsec.integrity import (
    digest_mismatches,
    parse_docker_diff,
    unexpected_changes,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
Runner = Callable[[list[str]], subprocess.CompletedProcess[str]]


def default_runner(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    """Execute command without shell using subprocess."""
    return subprocess.run(cmd, capture_output=True, text=True, check=False)  # noqa: S603


def parse_overrides(overrides: Sequence[str]) -> dict[str, str]:
    """Parse list of 'service=digest' strings into mapping."""
    result: dict[str, str] = {}
    for item in overrides:
        if "=" in item:
            svc, digest = item.split("=", 1)
            result[svc.strip()] = digest.strip()
    return result


def extract_mounts_and_pins(
    compose_path: Path,
    built_images_path: Path | None = None,
) -> tuple[dict[str, list[str]], dict[str, list[str]], dict[str, str]]:
    """Extract tmpfs mounts, volume mounts, and pinned digests from compose.yaml."""
    if not compose_path.exists():
        return {}, {}, {}

    data: dict[str, Any] = yaml.safe_load(compose_path.read_text()) or {}
    services = data.get("services", {})

    tmpfs_map: dict[str, list[str]] = {}
    volumes_map: dict[str, list[str]] = {}
    pinned_map: dict[str, str] = {}

    built_images: dict[str, str] = {}
    if built_images_path and built_images_path.exists():
        try:
            built_images = json.loads(built_images_path.read_text())
        except Exception:
            built_images = {}

    for name, svc in services.items():
        if not isinstance(svc, dict):
            continue

        # tmpfs
        tmpfs = svc.get("tmpfs", [])
        if isinstance(tmpfs, list):
            tmpfs_map[name] = [str(t) for t in tmpfs]
        elif isinstance(tmpfs, str):
            tmpfs_map[name] = [tmpfs]
        else:
            tmpfs_map[name] = []

        # volumes
        volumes: list[str] = []
        raw_volumes = svc.get("volumes", [])
        if isinstance(raw_volumes, list):
            for v in raw_volumes:
                if isinstance(v, str):
                    # host:container[:ro]
                    parts = v.split(":")
                    if len(parts) >= 2:
                        volumes.append(parts[1])
                    else:
                        volumes.append(parts[0])
                elif isinstance(v, dict) and "target" in v:
                    volumes.append(str(v["target"]))
        # Docker secrets are mounted read-only at /run/secrets/<target>.
        raw_secrets = svc.get("secrets", [])
        if isinstance(raw_secrets, list):
            for sec in raw_secrets:
                if isinstance(sec, str):
                    volumes.append(f"/run/secrets/{sec}")
                elif isinstance(sec, dict):
                    target = str(sec.get("target") or sec.get("source") or "")
                    if target:
                        path = target if target.startswith("/") else f"/run/secrets/{target}"
                        volumes.append(path)
        volumes_map[name] = volumes

        # pinned digests
        image = svc.get("image")
        if image and "@sha256:" in image:
            pinned_map[name] = image.split("@", 1)[1]
        elif image and "@" in image:
            pinned_map[name] = image.split("@", 1)[1]
        elif name in built_images:
            pinned_map[name] = built_images[name]

    return tmpfs_map, volumes_map, pinned_map


def check_integrity(
    compose_file: Path = REPO_ROOT / "compose.yaml",
    built_images_file: Path | None = REPO_ROOT / "data/run/built-images.json",
    pinned_overrides: Mapping[str, str] | None = None,
    runner: Runner = default_runner,
) -> tuple[int, list[str]]:
    """Run integrity check across running services.

    Returns:
        tuple of (exit_code, list of output lines)
    """
    tmpfs_map, volumes_map, pinned_map = extract_mounts_and_pins(compose_file, built_images_file)
    if pinned_overrides:
        pinned_map.update(pinned_overrides)

    # Find running services
    ps_res = runner(["docker", "compose", "ps", "--services", "--filter", "status=running"])
    if ps_res.returncode != 0:
        return 0, []

    running_services = [s.strip() for s in ps_res.stdout.splitlines() if s.strip()]
    lines: list[str] = []
    has_critical = False

    for svc in running_services:
        # Get container id
        cid_res = runner(["docker", "compose", "ps", "-q", svc])
        cid = cid_res.stdout.strip()
        if not cid:
            continue

        svc_critical = False

        # Check digest
        insp_res = runner(["docker", "inspect", cid])
        running_image_id: str | None = None
        if insp_res.returncode == 0:
            try:
                insp_data = json.loads(insp_res.stdout)
                if isinstance(insp_data, list) and insp_data:
                    running_image_id = insp_data[0].get("Image")
            except Exception:
                running_image_id = None

        if running_image_id and svc in pinned_map:
            mismatches = digest_mismatches(
                {svc: running_image_id},
                {svc: pinned_map[svc]},
            )
            if mismatches:
                svc_critical = True
                has_critical = True
                lines.append(f"CRITICAL {svc} digest mismatch")

        # Check docker diff
        diff_res = runner(["docker", "diff", cid])
        if diff_res.returncode == 0:
            changes = parse_docker_diff(diff_res.stdout)
            tmpfs = tmpfs_map.get(svc, [])
            volumes = volumes_map.get(svc, [])
            unexp = unexpected_changes(changes, tmpfs, volumes)
            if unexp:
                svc_critical = True
                has_critical = True
                lines.append(f"CRITICAL {svc} unexpected changes: {', '.join(unexp)}")

        if not svc_critical:
            lines.append(f"OK {svc}")

    return (1 if has_critical else 0), lines


def main() -> None:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description="Check container filesystem and digest integrity.")
    parser.add_argument(
        "--compose-file",
        type=Path,
        default=REPO_ROOT / "compose.yaml",
        help="Path to compose.yaml",
    )
    parser.add_argument(
        "--built-images",
        type=Path,
        default=REPO_ROOT / "data/run/built-images.json",
        help="Path to built-images.json",
    )
    parser.add_argument(
        "--pinned-override",
        action="append",
        default=[],
        help="Override pinned digest in format service=digest (can be passed multiple times)",
    )

    args = parser.parse_args()
    overrides = parse_overrides(args.pinned_override)

    code, lines = check_integrity(
        compose_file=args.compose_file,
        built_images_file=args.built_images,
        pinned_overrides=overrides,
    )
    for line in lines:
        print(line)
    sys.exit(code)


if __name__ == "__main__":
    main()
