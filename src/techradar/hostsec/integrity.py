"""Container filesystem and image integrity verification."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import PurePosixPath
from typing import Literal

Action = Literal["A", "C", "D"]


def parse_docker_diff(text: str) -> list[tuple[Action, str]]:
    """Parse docker diff output into a list of (Action, path) tuples.

    Docker diff output lines format:
    A /path (Added)
    C /path (Changed)
    D /path (Deleted)
    """
    changes: list[tuple[Action, str]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(maxsplit=1)
        if len(parts) == 2 and parts[0] in ("A", "C", "D"):
            changes.append((parts[0], parts[1]))  # type: ignore[arg-type]
    return changes


def unexpected_changes(
    changes: Sequence[tuple[str, str]],
    tmpfs: Sequence[str],
    volumes: Sequence[str],
) -> list[str]:
    """Find paths in changes that are not under any tmpfs or volume mount.

    Neither the mount directory itself nor any path underneath it is flagged.
    A folder that only holds a mount point (for example /etc/squid for a
    mounted /etc/squid/squid.conf) is not flagged either: Docker creates it to
    hold the mount. Any other file in that folder is still its own entry.
    """
    all_mounts = [PurePosixPath(m.rstrip("/")) for m in [*tmpfs, *volumes] if m.strip()]
    unexpected: list[str] = []

    for _action, path_str in changes:
        path = PurePosixPath(path_str)
        is_covered = False
        for mount in all_mounts:
            if path == mount or mount in path.parents or path in mount.parents:
                is_covered = True
                break
        if not is_covered:
            unexpected.append(path_str)

    return unexpected


def digest_mismatches(
    running: Mapping[str, str],
    pinned: Mapping[str, str],
) -> list[str]:
    """Return services whose running image digest differs from the pinned digest."""
    mismatches: list[str] = []
    for svc, run_digest in running.items():
        pin = pinned.get(svc)
        if pin is None or run_digest != pin:
            mismatches.append(svc)
    return mismatches
