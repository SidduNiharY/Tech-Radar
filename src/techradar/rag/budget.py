"""Token budgets that keep every prompt inside the model context (SEC-41).

Every model role runs with `num_ctx` 8192. When a prompt is longer, Ollama drops tokens from
the START, which is where the system prompt ("data, not instructions") and the opening
UNTRUSTED marker are. So every prompt built from book text must fit with room to spare.

`estimate_tokens` (words x 1.3) badly undercounts text with few spaces (OCR blobs, code) and
non-Latin scripts, so budgets here use `conservative_tokens`, which takes the largest of
three estimates: words x 1.3, characters / 3, and ASCII characters / 3 plus one token for
every non-ASCII character (Indic scripts often cost about a token per character).

SEC: SEC-37, SEC-41.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

NUM_CTX = 8192  # num_ctx of every role in infra/models/roles.yaml
# Chat-template tokens, the JSON-schema grammar and estimation error.
DEFAULT_MARGIN = 256


def conservative_tokens(text: str) -> int:
    """An upper-side token estimate that never trusts spaces or Latin script."""
    if not text:
        return 0
    non_ascii = sum(1 for c in text if ord(c) > 127)
    ascii_chars = len(text) - non_ascii
    return max(
        math.ceil(len(text.split()) * 1.3),
        math.ceil(len(text) / 3),
        math.ceil(ascii_chars / 3) + non_ascii,
    )


def context_budget(
    *,
    max_tokens: int,
    system_tokens: int,
    num_ctx: int = NUM_CTX,
    margin: int = DEFAULT_MARGIN,
) -> int:
    """Tokens left for the user prompt once the system prompt and the answer are reserved."""
    return max(0, num_ctx - max_tokens - system_tokens - margin)


def prompt_fits(
    system: str,
    user: str,
    *,
    max_tokens: int,
    num_ctx: int = NUM_CTX,
    margin: int = DEFAULT_MARGIN,
) -> bool:
    """True when system + user (conservative tokens) + max_tokens + margin fit in num_ctx."""
    used = conservative_tokens(system) + conservative_tokens(user)
    return used + max_tokens + margin <= num_ctx


def cut_to_tokens(text: str, budget: int) -> str:
    """The longest prefix of `text` within `budget` conservative tokens, cut at a space if near.

    Every estimate in `conservative_tokens` grows with the prefix length, so a binary search
    finds the longest prefix that fits.
    """
    if budget <= 0:
        return ""
    if conservative_tokens(text) <= budget:
        return text
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if conservative_tokens(text[:mid]) <= budget:
            lo = mid
        else:
            hi = mid - 1
    cut = text[:lo]
    space = max(cut.rfind(" "), cut.rfind("\n"))
    if space > 0 and space >= lo * 0.8:
        cut = cut[:space]
    return cut.rstrip()


def fit_texts(texts: Sequence[str], budget: int) -> list[str]:
    """Cut texts so their conservative tokens add up to at most `budget`, keeping their order.

    The budget is shared out evenly; a text smaller than its share is kept whole and gives the
    rest to the others, so short texts are never cut and only the longest ones shrink.
    """
    costs = [conservative_tokens(t) for t in texts]
    out = list(texts)
    remaining = max(0, budget)
    order = sorted(range(len(texts)), key=lambda i: costs[i])
    for k, i in enumerate(order):
        share = remaining // (len(order) - k)
        if costs[i] > share:
            out[i] = cut_to_tokens(texts[i], share)
        remaining -= conservative_tokens(out[i])
    return out
