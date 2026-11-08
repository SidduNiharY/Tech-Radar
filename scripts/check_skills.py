#!/usr/bin/env python3
"""Check skills and plugins against the allowlist."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

REPO_ROOT = Path(__file__).resolve().parent.parent


class AllowedExtension(BaseModel):
    name: str
    kind: Literal["skill", "plugin"]
    source: str
    commit: str
    sha256: str | None = None
    why: str


def read_skills_allowlist(agents_md: str) -> dict[str, AllowedExtension]:
    """Parse skills and plugins allowlist from AGENTS.md markdown content."""
    pattern = r"<!-- skills-allowlist:start -->(.*?)<!-- skills-allowlist:end -->"
    match = re.search(pattern, agents_md, re.DOTALL)
    if not match:
        return {}

    table_content = match.group(1).strip()
    lines = [line.strip() for line in table_content.splitlines() if line.strip()]

    extensions: dict[str, AllowedExtension] = {}
    for line in lines:
        if not line.startswith("|") or line.startswith("|---"):
            continue
        cols = [c.strip().strip("`") for c in line.split("|")[1:-1]]
        if len(cols) != 6:
            continue
        name, kind, source, commit, sha256_val, why = cols
        if name.lower() == "name" and kind.lower() == "kind":
            continue

        sha256 = None if sha256_val in ("-", "", "none", "None") else sha256_val
        extensions[name] = AllowedExtension(
            name=name,
            kind=kind,  # type: ignore[arg-type]
            source=source,
            commit=commit,
            sha256=sha256,
            why=why,
        )

    return extensions


def folder_hash(folder: Path) -> str:
    """Calculate SHA-256 over relative path and bytes of all files in sorted order."""
    hasher = hashlib.sha256()
    files = [p for p in folder.rglob("*") if p.is_file()]
    files.sort(key=lambda p: p.relative_to(folder).as_posix())

    for p in files:
        rel = p.relative_to(folder).as_posix()
        hasher.update(rel.encode("utf-8"))
        hasher.update(p.read_bytes())

    return hasher.hexdigest()


def skill_problems(repo: Path, allow: Mapping[str, AllowedExtension]) -> list[str]:
    """Identify unlisted or modified skills and unlisted plugins."""
    problems: list[str] = []

    # 1. Scan for skills (folders with SKILL.md, excluding tests/security/fixtures, .venv, .git)
    for skill_file in sorted(repo.rglob("SKILL.md")):
        rel = skill_file.relative_to(repo)
        if (
            "tests/security/fixtures" in rel.as_posix()
            or ".venv" in rel.parts
            or ".git" in rel.parts
        ):
            continue

        folder = skill_file.parent
        name = folder.name
        if name not in allow or allow[name].kind != "skill":
            problems.append(f"{name}: not allowed")
        else:
            entry = allow[name]
            if entry.sha256 and entry.sha256 != "-" and folder_hash(folder) != entry.sha256:
                problems.append(f"{name}: changed")

    # 2. Scan for plugins in committed agent settings
    claude_settings = repo / ".claude" / "settings.json"
    if claude_settings.is_file():
        try:
            with claude_settings.open("r", encoding="utf-8") as f:
                data = json.load(f)
            plugins = data.get("enabledPlugins", {})
            plugin_names: list[str] = []
            if isinstance(plugins, dict):
                plugin_names = [k for k, v in plugins.items() if v]
            elif isinstance(plugins, list):
                plugin_names = [str(p) for p in plugins]

            for plugin_name in plugin_names:
                if plugin_name not in allow or allow[plugin_name].kind != "plugin":
                    problems.append(f"{plugin_name}: not allowed")
        except Exception as e:
            problems.append(f"error parsing {claude_settings.relative_to(repo)}: {e}")

    return problems


def main() -> int:
    agents_path = REPO_ROOT / "AGENTS.md"
    if not agents_path.is_file():
        print(f"AGENTS.md not found: {agents_path}", file=sys.stderr)
        return 1

    allowlist = read_skills_allowlist(agents_path.read_text(encoding="utf-8"))
    problems = skill_problems(REPO_ROOT, allowlist)

    if problems:
        for p in problems:
            print(p, file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
