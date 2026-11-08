from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from techradar.pipeline.writer import slugify

SKILL_STATUSES: tuple[str, ...] = ("not_started", "learning", "built")

FRONTMATTER_PATTERN = re.compile(r"^---\r?\n(.*?)\r?\n---\r?\n", re.DOTALL)


def update_front_matter(
    md: str,
    updates: Mapping[str, Any],
    allowed_keys: frozenset[str],
) -> str:
    """Update YAML front matter while preserving the markdown body byte-for-byte.

    Raises ValueError if any key in `updates` is not present in `allowed_keys`.
    """
    for key in updates:
        if key not in allowed_keys:
            raise ValueError(f"Disallowed frontmatter key: {key}")

    match = FRONTMATTER_PATTERN.match(md)
    if match:
        fm_raw = match.group(1)
        body = md[match.end() :]
        existing_data = yaml.safe_load(fm_raw)
        if not isinstance(existing_data, dict):
            existing_data = {}
    else:
        existing_data = {}
        body = md

    # Apply updates
    for k, v in updates.items():
        existing_data[k] = v

    new_fm = yaml.safe_dump(existing_data, sort_keys=False).strip()
    return f"---\n{new_fm}\n---\n{body}"


async def set_skill_status(
    vault_root: Path,
    name: str,
    status: str,
    today: date,
) -> str:
    """Update skill status and updated timestamp in vault skill markdown."""
    if status not in SKILL_STATUSES:
        return "Status must be not_started, learning or built."

    slug = slugify(name)
    skill_file = vault_root / "skills" / f"{slug}.md"

    if not skill_file.is_file():
        return f"No skill page called {name}."

    content = skill_file.read_text(encoding="utf-8")
    updated = update_front_matter(
        content,
        {"status": status, "updated": today.isoformat()},
        frozenset({"status", "updated"}),
    )
    skill_file.write_text(updated, encoding="utf-8")
    return f"Updated {name}: {status}."
