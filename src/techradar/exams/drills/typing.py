from __future__ import annotations

import random
import string
from collections.abc import Sequence

from pydantic import BaseModel

_PRINTABLE_SET = set(string.printable) - {"\r", "\x0b", "\x0c"}


class TypingScore(BaseModel):
    key_depressions: int
    accuracy: float
    wpm: float


def _levenshtein(s1: str, s2: str) -> int:
    """Compute pure-Python Levenshtein edit distance with two rows."""
    if len(s1) < len(s2):
        return _levenshtein(s2, s1)
    if len(s2) == 0:
        return len(s1)

    previous_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        current_row = [i + 1] + [0] * len(s2)
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row[j + 1] = min(insertions, deletions, substitutions)
        previous_row = current_row

    return previous_row[-1]


def typing_passage(
    sentences: Sequence[str],
    rng: random.Random,
    target_keys: int = 2000,
) -> str:
    """Build a sanitized printable ASCII typing passage reaching target_keys."""
    cleaned: list[str] = []
    for s in sentences:
        filtered = "".join(c for c in s if c in _PRINTABLE_SET).strip()
        if filtered:
            cleaned.append(filtered)

    if not cleaned:
        cleaned = ["The quick brown fox jumps over the lazy dog."]

    shuffled = list(cleaned)
    rng.shuffle(shuffled)

    res_parts: list[str] = []
    total_len = 0
    idx = 0
    while total_len < target_keys:
        sentence = shuffled[idx % len(shuffled)]
        res_parts.append(sentence)
        total_len += len(sentence) + 1  # plus space
        idx += 1

    return " ".join(res_parts)


def score_typing(passage: str, typed: str, seconds: float) -> TypingScore:
    """Calculate key depressions, accuracy, and words per minute."""
    p_cap = passage[:3000]
    t_cap = typed[:3000]

    key_depressions = len(typed)

    if len(p_cap) == 0:
        accuracy = 1.0
    else:
        dist = _levenshtein(p_cap, t_cap)
        accuracy = max(0.0, 1.0 - dist / len(p_cap))

    if seconds > 0:
        minutes = seconds / 60.0
        wpm = (len(typed) / 5.0) / minutes
    else:
        wpm = 0.0

    return TypingScore(
        key_depressions=key_depressions,
        accuracy=accuracy,
        wpm=wpm,
    )
