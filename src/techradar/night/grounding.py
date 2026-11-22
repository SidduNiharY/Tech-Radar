"""Shared grounding steps for night pages: retrieve, drop weak excerpts, build the prompt, check.

Every generated page (foundation, deep dive, glossary, chain) is written from retrieved excerpts
only, cites them as [C#], and passes the same code checks as an answer (`check_citations`,
`override_flags`). Nothing here asks a model whether the page is grounded.

SEC: SEC-37, SEC-38, SEC-39.
"""

from __future__ import annotations

import dataclasses
import hashlib
import re
from collections.abc import Iterable, Sequence

from techradar.pipeline.writer import md_escape, slugify
from techradar.rag.answer import build_context, check_citations, fit_hits
from techradar.rag.budget import conservative_tokens, context_budget
from techradar.rag.retrieve import Hit, RagDeps, retrieve
from techradar.security.text import sanitize_text
from techradar.security.untrusted import override_flags, wrap_untrusted

MIN_SOURCES = 3
TOPIC_CHARS = 120
_MARKER = re.compile(r"\[C([0-9]+)\]")
_ESCAPED_MARKER = re.compile(r"\\\[C([0-9]+)\\\]")


def usable_hits(hits: Iterable[Hit], min_score: float = 0.0) -> list[Hit]:
    """Drop flagged and weak excerpts; a news excerpt counts only when it is verified."""
    return [
        h
        for h in hits
        if not h.flagged and h.score >= min_score and (h.doc_kind != "news" or h.verified is True)
    ]


def clean_topic(topic: str) -> str:
    """A topic as plain one-line text, safe to search and to show a model as data."""
    return " ".join(sanitize_text(topic).split())[:TOPIC_CHARS]


async def grounded_hits(topic: str, deps: RagDeps, *, k_final: int) -> list[Hit]:
    """Retrieve for `topic` with up to `k_final` hits, keeping only usable ones."""
    settings = deps.settings.model_copy(
        update={
            "rag_k_final": k_final,
            "rag_k_candidates": max(deps.settings.rag_k_candidates, k_final * 3),
        }
    )
    hits = await retrieve(clean_topic(topic), dataclasses.replace(deps, settings=settings))
    return usable_hits(hits, deps.settings.rag_min_score)


def build_prompt(label: str, topic: str, hits: Sequence[Hit]) -> str:
    """The user prompt: the excerpts and the topic, both inside UNTRUSTED markers."""
    return f"{build_context(hits)}\n\n{label}:\n{wrap_untrusted(clean_topic(topic))}"


def fit_for_prompt(
    hits: Sequence[Hit], system: str, topic: str, *, max_tokens: int, max_excerpts: int
) -> list[Hit]:
    """The best excerpts that fit the model context with room for the system prompt and answer."""
    room = context_budget(max_tokens=max_tokens, system_tokens=conservative_tokens(system))
    room -= conservative_tokens(build_prompt("Topic", topic, []))
    return fit_hits(hits, max(room, 0), max_excerpts)


def cites_ok(text: str, n_hits: int) -> bool:
    """True when `text` has at least one [C#] marker and every marker is a real excerpt."""
    return check_citations(text, [], n_hits)


def cited_numbers(texts: Iterable[str], listed: Iterable[str], n_hits: int) -> list[int] | None:
    """Sorted excerpt numbers cited by the texts and the model's list; None if any is invalid."""
    nums: set[int] = set()
    for text in texts:
        nums.update(int(m) for m in _MARKER.findall(text))
    for c in listed:
        m = re.fullmatch(r"C([0-9]+)", c)
        if not m:
            return None
        nums.add(int(m.group(1)))
    if any(n < 1 or n > n_hits for n in nums):
        return None
    return sorted(nums)


def flagged_text(texts: Iterable[str]) -> bool:
    """True when model-written text carries a high-confidence injection pattern."""
    return any(override_flags(t) for t in texts)


def escape_block(text: str) -> str:
    """Escape model-written text for a vault page but keep its [C#] markers readable."""
    return _ESCAPED_MARKER.sub(lambda m: f"[C{m.group(1)}]", md_escape(text))


def sources_lines(numbers: Sequence[int], hits: Sequence[Hit]) -> str:
    """`- [C#] title (path)` for each cited excerpt, escaped."""
    return "\n".join(
        f"- [C{n}] {md_escape(hits[n - 1].title[:200])} ({md_escape(hits[n - 1].doc_path)})"
        for n in numbers
    )


def safe_slug(text: str) -> str:
    """ASCII slug; text with no ASCII letters (Hindi, Telugu) gets a stable hash suffix."""
    slug = slugify(text)
    if slug == "note" and text.strip().lower() != "note":
        return f"note-{hashlib.sha256(text.encode('utf-8')).hexdigest()[:8]}"
    return slug
