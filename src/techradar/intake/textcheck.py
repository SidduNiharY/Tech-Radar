from __future__ import annotations

import re
from collections.abc import Sequence

from techradar.schemas.pipeline import IntakeStep

INJECTION_PATTERNS: dict[str, re.Pattern[str]] = {
    "ignore_previous": re.compile(
        r"ignore\s+(all\s+|any\s+|the\s+)?(previous|prior|above)\s+(instructions|prompts)",
        re.I,
    ),
    "disregard": re.compile(
        r"disregard\s+(all\s+|the\s+)?(previous|prior|above)",
        re.I,
    ),
    "you_are_now": re.compile(r"\byou\s+are\s+now\b", re.I),
    "system_prompt": re.compile(r"\bsystem\s+prompt\b", re.I),
    "role_tag": re.compile(r"^\s*(system|assistant)\s*:", re.I | re.M),
    "chat_template": re.compile(r"<\|im_start\|>", re.I),
    "address_jarvis": re.compile(r"\bjarvis\s*,", re.I),
    "tool_call": re.compile(r"\b(call|use|run)\s+(a\s+)?tool\b", re.I),
    "hide_from_user": re.compile(r"do\s+not\s+(tell|inform)\s+the\s+user", re.I),
}


def pattern_hits(text: str) -> list[str]:
    """Return sorted list of matched prompt injection pattern names."""
    return sorted(name for name, pat in INJECTION_PATTERNS.items() if pat.search(text))


def check_injection(
    score: float,
    hits: Sequence[str],
    *,
    flag_at: float = 0.5,
    quarantine_at: float = 0.98,
) -> IntakeStep:
    """Classify injection risk using model score and heuristic pattern matches (D34).

    Quarantines only on high classifier confidence AND multiple pattern hits.
    Never rejects - either ok, flag, or quarantine.
    """
    hit_list = list(hits)

    if score >= quarantine_at and len(hit_list) >= 2:
        return IntakeStep(
            name="injection",
            outcome="quarantine",
            detail=f"score={score:.2f}, hits={hit_list}",
        )

    if score >= flag_at or len(hit_list) > 0:
        return IntakeStep(
            name="injection",
            outcome="flag",
            detail=f"score={score:.2f}, hits={hit_list}",
        )

    return IntakeStep(name="injection", outcome="ok", detail=f"score={score:.2f}")
