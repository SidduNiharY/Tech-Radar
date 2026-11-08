"""Secure downloader for prompt guard models, restricting formats to safetensors only."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

FORBIDDEN_EXTENSIONS: tuple[str, ...] = (
    ".bin",
    ".pt",
    ".pth",
    ".pkl",
    ".pickle",
    ".ckpt",
)


def fetch_model(repo: str, revision: str, output_dir: Path) -> Path:
    """Download approved model files using Hugging Face hub snapshot."""
    import huggingface_hub

    output_dir.mkdir(parents=True, exist_ok=True)
    downloaded_path = huggingface_hub.snapshot_download(
        repo_id=repo,
        revision=revision,
        local_dir=str(output_dir),
        allow_patterns=[
            "*.safetensors",
            "*.json",
            "*.model",
            "*.txt",
            "vocab.*",
            "merges.txt",
        ],
    )

    # SEC-23: Verify no dangerous serialization files were downloaded
    for path in Path(downloaded_path).rglob("*"):
        if path.suffix.lower() in FORBIDDEN_EXTENSIONS:
            path.unlink(missing_ok=True)
            raise ValueError(f"SEC-23 Violation: Untrusted binary format detected: {path.name}")

    return Path(downloaded_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Download guard model in safetensors format")
    parser.add_argument("--repo", required=True, help="Hugging Face repo ID")
    parser.add_argument("--revision", required=True, help="Exact commit SHA")
    parser.add_argument("--output", default="/opt/models/guard", help="Output directory")
    args = parser.parse_args()

    try:
        fetch_model(args.repo, args.revision, Path(args.output))
        print(f"Successfully downloaded {args.repo}@{args.revision} to {args.output}")
    except Exception as exc:
        print(f"Failed to fetch model: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
