from __future__ import annotations

import re
import urllib.parse
from collections.abc import Sequence

from techradar.schemas.pipeline import IntakeStep
from techradar.security.urls import host_allowed

_LINK_RE = re.compile(
    r"""(?xi)
    (?:\[(?:[^\]]*)\]\(([^)]+)\))
    |
    (?:\b(?:https?://|javascript:|data:)[^\s<>"'\)]+)
"""
)


def extract_links(text: str) -> list[str]:
    """Extract URL and markdown hyperlinks from document text without fetching them."""
    links: list[str] = []
    for match in _LINK_RE.finditer(text):
        url = match.group(1) or match.group(0)
        cleaned = url.strip().split()[0]  # remove trailing markdown titles
        if cleaned:
            links.append(cleaned)
    return links


def check_links(links: Sequence[str], allowed_hosts: frozenset[str]) -> IntakeStep:
    """Validate links present in extracted text for dangerous schemes or excessive counts."""
    link_list = list(links)
    dangerous = [u for u in link_list if u.lower().startswith(("javascript:", "data:"))]
    if dangerous:
        return IntakeStep(
            name="links",
            outcome="flag",
            detail=f"dangerous link schemes: {len(dangerous)}",
        )

    if len(link_list) > 20:
        return IntakeStep(
            name="links",
            outcome="flag",
            detail=f"excessive links: {len(link_list)} > 20",
        )

    unallowlisted = 0
    for u in link_list:
        try:
            parsed = urllib.parse.urlsplit(u)
            host = (parsed.hostname or "").lower()
            if host and not host_allowed(host, allowed_hosts):
                unallowlisted += 1
        except Exception:
            unallowlisted += 1

    return IntakeStep(
        name="links",
        outcome="ok",
        detail=f"total={len(link_list)}, external={unallowlisted}",
    )
