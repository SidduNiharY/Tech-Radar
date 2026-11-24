"""The model call behind the politics view (Phase 7 Task 5).

Same isolation as the reader (SEC-16, SEC-22): the model has no tools, the articles are inside
UNTRUSTED markers, and its reply is a schema-checked JSON object that code then filters
(`keep_attributed`) and screens for injection before the writer sees it.

SEC: SEC-16, SEC-18, SEC-20, SEC-22.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from pydantic import BaseModel

from techradar.llm.client import Completer, LLMOutputError, complete_json
from techradar.llm.roles import Role
from techradar.pipeline.politics import POLITICS_SYSTEM, PoliticsView, keep_attributed
from techradar.rag.budget import conservative_tokens, context_budget, cut_to_tokens
from techradar.security.text import sanitize_text
from techradar.security.untrusted import injection_flags, wrap_untrusted

logger = logging.getLogger(__name__)

POLITICS_MAX_TOKENS = 900
MAX_ARTICLES = 4


def _strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, BaseModel):
        return [s for name in type(value).model_fields for s in _strings(getattr(value, name))]
    if isinstance(value, list):
        return [s for v in value for s in _strings(v)]
    return []


def build_articles(articles: Sequence[tuple[str, str, str]]) -> str:
    """`(domain, title, text)` of each article, cut to fit the context, inside one wrapper."""
    chosen = list(articles)[:MAX_ARTICLES]
    room = context_budget(
        max_tokens=POLITICS_MAX_TOKENS, system_tokens=conservative_tokens(POLITICS_SYSTEM)
    )
    per_article = max(room // max(len(chosen), 1) - 60, 0)
    parts = [
        f"Outlet: {domain}\nTitle: {sanitize_text(title)}\n\n"
        + cut_to_tokens(sanitize_text(text), per_article)
        for domain, title, text in chosen
    ]
    return wrap_untrusted("\n\n---\n\n".join(parts))


async def build_politics_view(
    completer: Completer, articles: Sequence[tuple[str, str, str]]
) -> PoliticsView | None:
    """The facts, supporters and critics of one story, or None when the model fails or is flagged.

    Opinions of an outlet that is not among `articles` are dropped; the view is never built from
    the model's own claim about who said what.
    """
    if not articles:
        return None
    domains = {domain for domain, _, _ in articles}
    try:
        view = await complete_json(
            completer,
            Role.WORKER,
            POLITICS_SYSTEM,
            build_articles(articles),
            PoliticsView,
            max_tokens=POLITICS_MAX_TOKENS,
        )
    except LLMOutputError:
        return None
    except Exception:  # an outage must not stop the note being written without opinions
        logger.warning("politics view failed; the note is written without it", exc_info=True)
        return None
    if any(injection_flags(s) for s in _strings(view)):
        return None
    return keep_attributed(view, domains)
