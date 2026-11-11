"""Pinned image digests must look like real registry digests (SEC-55).

The compose policy test only checks that a digest is present. Generated
placeholders such as `sha256:b6c5d4e3f2a1b6c5...` (a repeating block) or
`sha256:c2b3a4f5e6d7a8b9...` (a counting pattern) passed it, and every
container failed to pull on the server. A real sha256 is random, so it
almost never repeats an 8-character block or counts up for 6 pairs.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PIN = re.compile(r"([\w./:-]+)@sha256:([0-9a-f]+)")


def pinned_images() -> list[tuple[str, str, str]]:
    files = [ROOT / "compose.yaml", ROOT / "compose.dev.yaml"]
    files += sorted((ROOT / "infra").rglob("Dockerfile*"))
    files += sorted((ROOT / "security" / "simulate").glob("*.sh"))
    found = []
    for path in files:
        if not path.is_file():
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for match in PIN.finditer(line):
                found.append((f"{path.relative_to(ROOT)}:{lineno}", match.group(1), match.group(2)))
    return found


def looks_fake(digest: str) -> str | None:
    if len(digest) != 64:
        return "not 64 hex characters"
    for start in range(len(digest) - 8):
        if digest.count(digest[start : start + 8]) > 1:
            return f"repeats the block {digest[start : start + 8]!r}"
    run = 0
    for i in range(1, len(digest) // 2):
        prev, cur = digest[2 * i - 1], digest[2 * i + 1]
        if prev.isdigit() and cur.isdigit() and (int(prev) + 1) % 10 == int(cur):
            run += 1
            if run >= 6:
                return "counts up like a placeholder"
        else:
            run = 0
    return None


def test_there_are_pinned_images():
    assert len(pinned_images()) >= 9


def test_every_pinned_digest_looks_real():
    problems = [
        f"{where}: {image} ({reason})"
        for where, image, digest in pinned_images()
        if (reason := looks_fake(digest))
    ]
    assert problems == []


def test_detector_flags_known_placeholders():
    assert looks_fake("b6c5d4e3f2a1" * 5 + "b6c5")
    assert looks_fake("c2b3a4f5e6d7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b3")
    assert looks_fake("abc") == "not 64 hex characters"
    real = "251f814864b3ed17ea8740b89a00363c5f14a3ca3738644fdec622eea78d3305"
    assert looks_fake(real) is None
