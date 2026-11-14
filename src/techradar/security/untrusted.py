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


# For text a model WROTE from an untrusted document (summaries, eval questions): only the
# high-confidence patterns. The broader set above also matches everyday programming prose
# ("use a Python function", "run the command", "act as a linker", "system prompt") and would
# fail every chapter of a coding book. Wherever this text is read again it is wrapped as
# untrusted data, so this check is defence in depth, not the only barrier.
_OVERRIDE_NAMES = ("ignore_instructions", "exfil_link")
_YOU_ARE_NOW = re.compile(r"\byou are now\b", re.IGNORECASE)
_MD_LINK = re.compile(r"\[[^\]]*\]\([^)]*\)")


def override_flags(text: str) -> list[str]:
    """Names of high-confidence injection patterns in model-written text (see above)."""
    flags = {
        n for n, pat in INJECTION_PATTERNS.items() if n in _OVERRIDE_NAMES and pat.search(text)
    }
    if _YOU_ARE_NOW.search(text):
        flags.add("role_override")
    if _MD_LINK.search(text):
        flags.add("exfil_link")
    return sorted(flags)
