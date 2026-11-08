from __future__ import annotations

import re
import unicodedata
from typing import Literal


def _is_indic(c: str) -> bool:
    code = ord(c)
    return (0x0900 <= code <= 0x097F) or (0x0C00 <= code <= 0x0C7F)


def sanitize_text(s: str) -> str:
    """Sanitize text by applying NFKC, removing control and zero-width/bidi chars,

    preserving Indic ZWJ/ZWNJ when between Indic characters, collapsing newlines.
    """
    if not s:
        return ""

    normalized = unicodedata.normalize("NFKC", s)
    chars = list(normalized)
    result: list[str] = []

    for i, c in enumerate(chars):
        code = ord(c)
        cat = unicodedata.category(c)

        # Remove Cc except newline and tab
        if cat == "Cc" and c not in ("\n", "\t"):
            continue

        # Tag characters U+E0000 - U+E007F
        if 0xE0000 <= code <= 0xE007F:
            continue

        # Cf characters (zero-width, bidi, soft hyphen)
        if cat == "Cf":
            if c in ("\u200c", "\u200d"):
                if (
                    i > 0
                    and i < len(chars) - 1
                    and _is_indic(chars[i - 1])
                    and _is_indic(chars[i + 1])
                ):
                    result.append(c)
                continue
            continue

        result.append(c)

    cleaned = "".join(result)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def detect_lang(s: str) -> Literal["en", "hi", "te", "other"]:
    """Detect language based on letter character frequencies."""
    letters = [c for c in s if unicodedata.category(c).startswith("L")]
    if not letters:
        return "other"

    total = len(letters)
    devanagari = sum(1 for c in letters if 0x0900 <= ord(c) <= 0x097F)
    telugu = sum(1 for c in letters if 0x0C00 <= ord(c) <= 0x0C7F)
    latin = sum(1 for c in letters if "LATIN" in unicodedata.name(c, ""))

    if devanagari / total > 0.30:
        return "hi"
    if telugu / total > 0.30:
        return "te"
    if latin / total > 0.50:
        return "en"
    return "other"
