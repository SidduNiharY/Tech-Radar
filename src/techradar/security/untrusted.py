from __future__ import annotations

import re
import secrets

INJECTION_PATTERNS: dict[str, re.Pattern[str]] = {
    "ignore_instructions": re.compile(
        r"\b(ignore|disregard|forget)\b.{0,40}\b(previous|above|prior|earlier|all)\b.{0,20}\b(instructions?|prompts?|rules?)\b",
        re.IGNORECASE | re.DOTALL,
    ),
    "role_override": re.compile(
        r"\byou are now\b|\bact as\b|\bnew instructions?\b",
        re.IGNORECASE,
    ),
    "system_prompt": re.compile(
        r"\bsystem prompt\b|\bdeveloper message\b",
        re.IGNORECASE,
    ),
    "tool_request": re.compile(
        r"\b(call|use|run|execute)\b.{0,20}\b(tool|function|command|shell|python)\b",
        re.IGNORECASE | re.DOTALL,
    ),
    "exfil_link": re.compile(
        r"https?://|www\.|!\[|\]\(",
        re.IGNORECASE,
    ),
}


def wrap_untrusted(text: str) -> str:
    """Wrap untrusted text in boundary markers with random token."""
    b = secrets.token_hex(8)
    while b in text:
        b = secrets.token_hex(8)
    return f"<<UNTRUSTED {b}>>\n{text}\n<<END {b}>>"


def injection_flags(text: str) -> list[str]:
    """Return sorted list of matched injection pattern names."""
    return sorted(name for name, pat in INJECTION_PATTERNS.items() if pat.search(text))
