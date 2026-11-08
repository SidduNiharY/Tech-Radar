#!/usr/bin/env python3
"""Fetch and verify openWakeWord ONNX models for browser-side wake word detection.

SEC: Validates SHA-256 checksums from infra/models/wakeword.yaml.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "infra" / "models" / "wakeword.yaml"
OUTPUT_DIR = REPO_ROOT / "apps/web/public/models/openwakeword"


def sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def verify_models(config: dict, target_dir: Path) -> bool:
    all_ok = True
    models = config.get("models", {})
    for name, spec in models.items():
        fname = spec.get("filename", f"{name}.onnx")
        dest = target_dir / fname
        expected_sha = spec.get("sha256")
        if not dest.is_file():
            print(f"[MISSING] {fname} not found in {target_dir}")
            all_ok = False
            continue

        actual_sha = sha256_of_file(dest)
        if actual_sha != expected_sha:
            print(f"[CHECKSUM MISMATCH] {fname}: expected {expected_sha}, got {actual_sha}")
            all_ok = False
        else:
            print(f"[OK] {fname} verified ({dest.stat().st_size} bytes)")

    return all_ok


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch and verify openWakeWord ONNX models.")
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Only verify existing models on disk without downloading.",
    )
    args = parser.parse_args()

    if not CONFIG_PATH.is_file():
        print(f"Error: Missing config at {CONFIG_PATH}", file=sys.stderr)
        return 1

    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.verify_only:
        ok = verify_models(config, OUTPUT_DIR)
        return 0 if ok else 1

    print(f"Checking openWakeWord models in {OUTPUT_DIR}...")
    models = config.get("models", {})
    all_present = True
    for name, spec in models.items():
        fname = spec.get("filename", f"{name}.onnx")
        dest = OUTPUT_DIR / fname
        if not dest.is_file():
            all_present = False
            print(f"Model {fname} needs fetch (or offline download).")

    if all_present:
        return 0 if verify_models(config, OUTPUT_DIR) else 1

    print("All required models registered in infra/models/wakeword.yaml.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
