#!/usr/bin/env python3
"""Check dependencies against approved allowlist."""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from collections.abc import Sequence
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent


def normalize(name: str) -> str:
    """PEP 503 normalization: lowercase, runs of [-_.] become -."""
    return re.sub(r"[-_.]+", "-", name).lower()


def _strip_specifier(item: str) -> str:
    """Strip extras, version specifiers, markers, and urls from a dependency requirement."""
    split_parts = re.split(r"[\[<>=!~;@\s]", item)
    return split_parts[0].strip()


def direct_python_deps(pyproject: dict) -> set[str]:
    """Extract direct dependencies from pyproject.toml dict, normalized."""
    deps: set[str] = set()

    project = pyproject.get("project", {})
    # 1. project.dependencies
    for req in project.get("dependencies", []):
        if isinstance(req, str):
            clean = _strip_specifier(req)
            if clean:
                deps.add(normalize(clean))

    # 2. project.optional-dependencies
    for group in project.get("optional-dependencies", {}).values():
        if isinstance(group, list):
            for req in group:
                if isinstance(req, str):
                    clean = _strip_specifier(req)
                    if clean:
                        deps.add(normalize(clean))

    # 3. dependency-groups
    for group in pyproject.get("dependency-groups", {}).values():
        if isinstance(group, list):
            for req in group:
                if isinstance(req, str):
                    clean = _strip_specifier(req)
                    if clean:
                        deps.add(normalize(clean))

    return deps


def direct_npm_deps(package_json: dict) -> set[str]:
    """Extract direct dependencies from package.json dict, normalized."""
    deps: set[str] = set()
    for key in ("dependencies", "devDependencies"):
        deps_dict = package_json.get(key, {})
        if isinstance(deps_dict, dict):
            for name in deps_dict:
                deps.add(normalize(name))
    return deps


def unapproved(found: set[str], approved: set[str]) -> list[str]:
    """Return sorted list of found dependencies that are not approved."""
    return sorted(found - approved)


def damerau_levenshtein(s1: str, s2: str) -> int:
    """Calculate the Damerau-Levenshtein distance between two strings."""
    d: dict[tuple[int, int], int] = {}
    len1 = len(s1)
    len2 = len(s2)
    for i in range(-1, len1 + 1):
        d[(i, -1)] = i + 1
    for j in range(-1, len2 + 1):
        d[(-1, j)] = j + 1

    for i in range(len1):
        for j in range(len2):
            cost = 0 if s1[i] == s2[j] else 1
            d[(i, j)] = min(
                d[(i - 1, j)] + 1,  # deletion
                d[(i, j - 1)] + 1,  # insertion
                d[(i - 1, j - 1)] + cost,  # substitution
            )
            if i > 0 and j > 0 and s1[i] == s2[j - 1] and s1[i - 1] == s2[j]:
                d[(i, j)] = min(d[(i, j)], d[(i - 2, j - 2)] + 1)  # transposition

    return d[(len1 - 1, len2 - 1)]


def lookalikes(name: str, popular: Sequence[str], max_distance: int = 2) -> list[str]:
    """Return popular names at Damerau-Levenshtein distance 1 to max_distance."""
    norm_name = normalize(name)
    results: list[str] = []
    seen: set[str] = set()

    for pop in popular:
        norm_pop = normalize(pop)
        if norm_pop == norm_name:
            continue
        if abs(len(norm_name) - len(norm_pop)) > max_distance:
            continue
        dist = damerau_levenshtein(norm_name, norm_pop)
        if 1 <= dist <= max_distance and norm_pop not in seen:
            results.append(norm_pop)
            seen.add(norm_pop)

    return sorted(results)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check dependencies against approved list.")
    parser.add_argument("--pyproject", action="append", help="Path to pyproject.toml")
    parser.add_argument("--package-json", action="append", help="Path to package.json")
    parser.add_argument(
        "--approved",
        default=str(REPO_ROOT / "infra" / "policy" / "approved_deps.yaml"),
        help="Path to approved_deps.yaml",
    )
    parser.add_argument(
        "--popular",
        default=str(REPO_ROOT / "infra" / "policy" / "popular_packages.txt"),
        help="Path to popular_packages.txt",
    )

    args = parser.parse_args(argv)

    approved_path = Path(args.approved)
    if not approved_path.is_file():
        print(f"Approved deps file not found: {approved_path}", file=sys.stderr)
        return 1

    with approved_path.open("r", encoding="utf-8") as f:
        approved_data = yaml.safe_load(f) or {}

    approved_python = {normalize(k) for k in (approved_data.get("python") or {})}
    approved_npm = {normalize(k) for k in (approved_data.get("npm") or {})}

    popular_packages: list[str] = []
    popular_path = Path(args.popular)
    if popular_path.is_file():
        with popular_path.open("r", encoding="utf-8") as f:
            popular_packages = [line.strip() for line in f if line.strip()]

    failed = False

    # Check python dependencies
    pyproject_paths = args.pyproject
    if not pyproject_paths:
        default_pyproject = REPO_ROOT / "pyproject.toml"
        if default_pyproject.is_file():
            pyproject_paths = [str(default_pyproject)]

    if pyproject_paths:
        for p_str in pyproject_paths:
            p_path = Path(p_str)
            if not p_path.is_file():
                continue
            with p_path.open("rb") as f:
                data = tomllib.load(f)
            found = direct_python_deps(data)
            unapp = unapproved(found, approved_python)
            for pkg in unapp:
                failed = True
                looks = lookalikes(pkg, popular_packages)
                if looks:
                    print(f"unapproved: {pkg} (looks like: {', '.join(looks)})")
                else:
                    print(f"unapproved: {pkg}")

    # Check npm dependencies
    pkg_json_paths = args.package_json
    if not pkg_json_paths:
        default_pkg_json = REPO_ROOT / "package.json"
        if default_pkg_json.is_file():
            pkg_json_paths = [str(default_pkg_json)]

    if pkg_json_paths:
        for p_str in pkg_json_paths:
            p_path = Path(p_str)
            if not p_path.is_file():
                continue
            with p_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            found = direct_npm_deps(data)
            unapp = unapproved(found, approved_npm)
            for pkg in unapp:
                failed = True
                looks = lookalikes(pkg, popular_packages)
                if looks:
                    print(f"unapproved: {pkg} (looks like: {', '.join(looks)})")
                else:
                    print(f"unapproved: {pkg}")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
