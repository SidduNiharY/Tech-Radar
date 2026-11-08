from __future__ import annotations

from pathlib import Path

import yaml

from techradar.schemas.pipeline import SourceSpec
from techradar.security.urls import check_url


def load_sources(path: Path, allowed: frozenset[str]) -> list[SourceSpec]:
    """Load and validate source specifications from YAML file against allowlist."""
    content = path.read_text(encoding="utf-8")
    raw = yaml.safe_load(content)
    if not isinstance(raw, list):
        raise ValueError("Sources file must contain a list of source specifications")

    sources: list[SourceSpec] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        url = item.get("url", "")
        # Validate URL against allowlist; raises UrlRejected if invalid
        check_url(url, allowed)
        sources.append(SourceSpec.model_validate(item))
    return sources
