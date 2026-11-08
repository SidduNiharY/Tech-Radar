"""Generate Falco YAML lists and macros from expected_programs.yaml."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import yaml


def build_lists(expected: dict[str, Any]) -> str:
    """Generate Falco YAML lists for each service and the tr_app_container macro."""
    blocks: list[str] = []

    services = expected.get("services", {})
    for svc in sorted(services.keys()):
        progs = services[svc]
        progs_str = ", ".join(progs)
        blocks.append(f"- list: tr_{svc}_programs\n  items: [{progs_str}]")

    excluded = expected.get("excluded_profiles", [])
    if excluded:
        excluded_cond = " or ".join(f'container.name startswith "techradar-{p}"' for p in excluded)
        condition = f'(container.name startswith "techradar-" and not ({excluded_cond}))'
    else:
        condition = '(container.name startswith "techradar-")'

    blocks.append(f"- macro: tr_app_container\n  condition: {condition}")

    return "\n\n".join(blocks) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Falco lists from expected_programs.yaml")
    parser.add_argument(
        "--expected",
        type=Path,
        default=Path("infra/falco/expected_programs.yaml"),
        help="Path to expected_programs.yaml",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("infra/falco/generated_lists.yaml"),
        help="Path to generated_lists.yaml",
    )
    args = parser.parse_args(argv)

    expected_path: Path = args.expected
    output_path: Path = args.output

    if not expected_path.exists():
        sys.stderr.write(f"Error: {expected_path} does not exist\n")
        return 1

    expected_data = yaml.safe_load(expected_path.read_text())
    content = build_lists(expected_data)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content)
    return 0


if __name__ == "__main__":
    sys.exit(main())
