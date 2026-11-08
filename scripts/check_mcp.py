#!/usr/bin/env python3
"""Check committed MCP server configurations against the allowlist."""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Mapping
from pathlib import Path

from pydantic import BaseModel

REPO_ROOT = Path(__file__).resolve().parent.parent


class AllowedServer(BaseModel):
    name: str
    command: str
    version: str
    access: str
    why: str


def read_allowlist(agents_md: str) -> dict[str, AllowedServer]:
    """Parse MCP server allowlist from AGENTS.md markdown content."""
    pattern = r"<!-- mcp-allowlist:start -->(.*?)<!-- mcp-allowlist:end -->"
    match = re.search(pattern, agents_md, re.DOTALL)
    if not match:
        return {}

    table_content = match.group(1).strip()
    lines = [line.strip() for line in table_content.splitlines() if line.strip()]

    servers: dict[str, AllowedServer] = {}
    for line in lines:
        if not line.startswith("|") or line.startswith("|---"):
            continue
        cols = [c.strip().strip("`") for c in line.split("|")[1:-1]]
        if len(cols) != 5:
            continue
        name, command, version, access, why = cols
        if name.lower() == "name" and command.lower() == "command":
            continue
        servers[name] = AllowedServer(
            name=name,
            command=command,
            version=version,
            access=access,
            why=why,
        )

    return servers


def mcp_problems(config: dict, allow: Mapping[str, AllowedServer]) -> list[str]:
    """Identify violations in an MCP server configuration."""
    problems: list[str] = []
    servers = config.get("mcpServers", {})
    if not isinstance(servers, dict):
        return problems

    for name, srv in servers.items():
        if not isinstance(srv, dict):
            continue

        if name not in allow:
            problems.append(f"{name}: not allowed")
            continue

        cmd = srv.get("command", "")
        args = srv.get("args", [])

        # Check for unpinned versions
        is_unpinned = False
        if "@latest" in cmd or any("@latest" in str(arg) for arg in args):
            is_unpinned = True
        elif cmd in ("uvx", "npx") or any(arg in ("uvx", "npx") for arg in args):
            # Check package spec in args
            for arg in args:
                arg_str = str(arg).strip()
                if arg_str.startswith("-"):
                    continue
                if "@latest" in arg_str:
                    is_unpinned = True
                    break
                if "@" not in arg_str and "==" not in arg_str:
                    is_unpinned = True
                    break
                ver = arg_str.split("@")[-1] if "@" in arg_str else arg_str.split("==")[-1]
                if not ver or ver == "latest":
                    is_unpinned = True
                    break
                # Valid pinned package found
                break

        if is_unpinned:
            problems.append(f"{name}: not pinned")

        # Check for secrets in environment variables
        env = srv.get("env", {})
        if isinstance(env, dict):
            for k, v in env.items():
                if any(sub in k.upper() for sub in ("TOKEN", "KEY", "SECRET")):
                    if not isinstance(v, str) or not re.match(r"^\$\{[^}]+\}$", v.strip()):
                        problems.append(f"{name}: secret in config")
                        break

    return problems


def main() -> int:
    agents_path = REPO_ROOT / "AGENTS.md"
    if not agents_path.is_file():
        print(f"AGENTS.md not found: {agents_path}", file=sys.stderr)
        return 1

    allowlist = read_allowlist(agents_path.read_text(encoding="utf-8"))

    mcp_config_paths = [
        REPO_ROOT / ".mcp.json",
        REPO_ROOT / ".cursor" / "mcp.json",
        REPO_ROOT / ".vscode" / "mcp.json",
        REPO_ROOT / ".gemini" / "settings.json",
        REPO_ROOT / "mcp_config.json",
    ]

    all_problems: list[str] = []
    for path in mcp_config_paths:
        if not path.is_file():
            continue
        try:
            with path.open("r", encoding="utf-8") as f:
                config = json.load(f)
            problems = mcp_problems(config, allowlist)
            for p in problems:
                all_problems.append(f"{path.relative_to(REPO_ROOT)}: {p}")
        except Exception as e:
            all_problems.append(f"{path.relative_to(REPO_ROOT)}: error parsing JSON: {e}")

    if all_problems:
        for p in all_problems:
            print(p, file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
