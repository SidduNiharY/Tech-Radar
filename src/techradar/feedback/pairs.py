"""Which-is-better comparison pairs generation and human preference evaluation."""

from __future__ import annotations

import secrets
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import PreferencePair
from techradar.feedback.rules import StyleRule
from techradar.messaging.outbox import Button

VARIANTS: list[tuple[str, str, StyleRule, StyleRule]] = [
    (
        "short",
        "detailed",
        StyleRule(mode=None, field="length", value="short"),
        StyleRule(mode=None, field="length", value="long"),
    ),
    (
        "example_first",
        "definition_first",
        StyleRule(mode=None, field="order", value="example_first"),
        StyleRule(mode=None, field="order", value="definition_first"),
    ),
]


def pair_due(asked_this_week: int, asked_today: int) -> bool:
    """Return True only if weekly limit (<3) and daily limit (<1) are respected."""
    return asked_this_week < 3 and asked_today < 1


async def make_pair(
    completer: Any,
    question: str,
    excerpts: Sequence[Any],
    variant: tuple[str, str, StyleRule, StyleRule],
    role: Any = None,
) -> tuple[str, str] | None:
    """Two answers from the same excerpts, one per style rule, each vetted like any answer.

    The question is sanitized, the request must fit the context, and every draft goes through
    the same `vet_draft` as `answer_question` (not found, citations, injection flags). The pair
    is dropped when any check fails, when a draft cites an unverified note, or when any excerpt
    is flagged by the Intake Gateway (SEC-37, SEC-38, SEC-41). `excerpts` are the retrieved
    `Hit`s; the style rules are fixed templates.
    """
    from techradar.llm.client import LLMOutputError, complete_json
    from techradar.llm.roles import Role
    from techradar.profile.style import render_profile_block
    from techradar.rag.answer import (
        ANSWER_MAX_TOKENS,
        ANSWER_SYSTEM,
        AnswerDraft,
        _context_tokens,
        fit_request,
        vet_draft,
    )
    from techradar.security.text import sanitize_text

    hits = list(excerpts)
    clean = sanitize_text(question)
    if not hits or not clean or any(h.flagged for h in hits):
        return None
    systems = [f"{ANSWER_SYSTEM}\n\n{render_profile_block([r])}" for r in (variant[2], variant[3])]
    longest = max(systems, key=len)  # both versions get the same excerpts
    fitted = fit_request(hits, clean, longest, (), _context_tokens(clean, longest), hits[0])
    if fitted is None:
        return None
    fitted_hits, prompt = fitted
    texts: list[str] = []
    for system in systems:
        try:
            draft = await complete_json(
                completer,
                role or Role.WORKER,
                system,
                prompt,
                AnswerDraft,
                max_tokens=ANSWER_MAX_TOKENS,
            )
        except LLMOutputError:
            return None
        vetted = vet_draft(draft, fitted_hits)
        if vetted.status != "answered" or vetted.used_unverified or vetted.flags:
            return None
        texts.append(vetted.text)
    return texts[0], texts[1]


def format_pair_message(
    question: str,
    ans_a: str,
    ans_b: str,
    pair_id: int,
) -> tuple[str, list[list[Button]]]:
    """Format Telegram comparison message and voting inline buttons."""
    text = f"Which is better?\nA: {ans_a[:1800]}\n\nB: {ans_b[:1800]}"
    buttons: list[list[Button]] = [
        [
            Button(text="A", data=f"pair:{pair_id}:1"),
            Button(text="B", data=f"pair:{pair_id}:2"),
            Button(text="Skip", data=f"pair:{pair_id}:3"),
        ]
    ]
    return text, buttons


async def create_pair(
    session: AsyncSession,
    *,
    mode: str,
    question: str,
    version_a: str,
    version_b: str,
    variant_a: str,
    variant_b: str,
) -> int:
    """Store new preference pair in database."""
    pair = PreferencePair(
        mode=mode,
        question=question,
        version_a=version_a,
        version_b=version_b,
        variant_a=variant_a,
        variant_b=variant_b,
        chosen=None,
    )
    session.add(pair)
    await session.flush()
    return pair.id


CHOICES: dict[int, Literal["a", "b", "skip"]] = {1: "a", 2: "b", 3: "skip"}


async def record_pair_choice(
    session: AsyncSession,
    pair_id: int,
    chosen: Literal["a", "b", "skip"],
    now: datetime | None = None,
) -> bool:
    """Record the owner's choice once. An answered pair is never changed. True when recorded."""
    ts = now or datetime.now(UTC)
    res = await session.execute(select(PreferencePair).where(PreferencePair.id == pair_id))
    pair = res.scalar_one_or_none()
    if pair is None or pair.chosen is not None:
        return False
    pair.chosen = chosen
    pair.answered_at = ts
    await session.flush()
    return True


async def pair_counts(session: AsyncSession, now: datetime, tz: str) -> tuple[int, int]:
    """(pairs asked in the last 7 days, pairs asked on today's local date)."""
    from zoneinfo import ZoneInfo

    rows = (
        (
            await session.execute(
                select(PreferencePair.asked_at).where(
                    PreferencePair.asked_at >= now - timedelta(days=7)
                )
            )
        )
        .scalars()
        .all()
    )
    zone = ZoneInfo(tz)
    today = now.astimezone(zone).date()
    return len(rows), sum(1 for r in rows if r.astimezone(zone).date() == today)


async def run_pair(
    session: AsyncSession,
    completer: Any,
    hits: Sequence[Any],
    question: str,
    *,
    mode: str,
    owner_chat_id: int,
    now: datetime,
    tz: str,
) -> int | None:
    """After an answered ask: send one "Which is better?" pair when the limits allow it.

    At most 3 a week and 1 a day, rotating the two variants, never without two checked
    answers. Returns the pair id, or None when nothing was sent.
    """
    from techradar.messaging.outbox import enqueue_message

    week, today = await pair_counts(session, now, tz)
    if not pair_due(week, today) or not hits:
        return None
    variant = VARIANTS[week % len(VARIANTS)]
    pair = await make_pair(completer, question, hits, variant)
    if pair is None:
        return None
    first, second = (variant[0], variant[1]), (pair[0], pair[1])
    if secrets.randbelow(2):  # which version is A is random, so the first position never wins
        first, second = (first[1], first[0]), (second[1], second[0])
    pair_id = await create_pair(
        session,
        mode=mode,
        question=question[:500],
        version_a=second[0],
        version_b=second[1],
        variant_a=first[0],
        variant_b=first[1],
    )
    text, buttons = format_pair_message(question, second[0], second[1], pair_id)
    await enqueue_message(
        session,
        chat_id=owner_chat_id,
        text=text,
        purpose="pair",
        buttons=buttons,
        ref_id=pair_id,
    )
    return pair_id
