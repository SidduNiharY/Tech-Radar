#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

FORBIDDEN_EXTENSIONS: set[str] = {".pt", ".pth", ".pkl", ".ckpt"}


def run_checker(root: Path) -> int:
    """Check directory for unapproved pickle or unsafe model weight files."""
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        ext = p.suffix.lower()
        if ext in FORBIDDEN_EXTENSIONS:
            print(f"Forbidden model file found: {p}", file=sys.stderr)
            return 1
        if ext == ".bin":
            parent = p.parent
            # Allowed in CTranslate2 directory: contains config.json and model.bin
            is_ct2 = (parent / "config.json").exists() and p.name == "model.bin"
            # Allowed in wav2vec2 directory if safetensors or torch 2.6
            is_w2v2 = "wav2vec2" in str(parent).lower()
            if not (is_ct2 or is_w2v2):
                print(f"Unverified .bin model weights found: {p}", file=sys.stderr)
                return 1
    return 0


def main() -> None:
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    sys.exit(run_checker(target))


if __name__ == "__main__":
    main()
