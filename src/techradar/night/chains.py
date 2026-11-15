from __future__ import annotations

import re
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field

_SAFE_CHARS = re.compile(r"[^\w\s.,%₹$()\-]")


def sanitize_label(s: str, max_length: int = 60) -> str:
    """Sanitize a Mermaid node label: alphanumeric, spaces, and safe punctuation only."""
    # Remove any tags, quotes, or dangerous keywords
    cleaned = re.sub(r"(?i)(click|style|classDef|script|iframe|http[s]?://)", "", s)
    cleaned = _SAFE_CHARS.sub("", cleaned)
    # Collapse consecutive spaces
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:max_length]


class CausalChain(BaseModel):
    model_config = ConfigDict(frozen=True)

    steps: list[str] = Field(min_length=3, max_length=6)
    citations: list[str]


def chain_to_mermaid(steps: Sequence[str]) -> str:
    """Render a sequence of causal events as a Mermaid flowchart diagram."""
    if not steps:
        return "flowchart LR"

    nodes: list[str] = []
    for i, step in enumerate(steps, start=1):
        clean_text = sanitize_label(step)
        nodes.append(f's{i}["{clean_text}"]')

    links = " --> ".join(nodes)
    return f"flowchart LR\n  {links}"
