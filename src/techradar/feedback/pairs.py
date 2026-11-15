"""Which-is-better comparison pairs generation and human preference evaluation."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field
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


def _has_valid_citations(text: str) -> bool:
    """Check that answer text contains citations."""
    return bool("[c" in text.lower() or "[1]" in text or "[c1]" in text.lower())


class PairAnswer(BaseModel):
    """Answer draft with citations for pair comparison."""

    text: str
    citations: list[str] = Field(default_factory=list)


async def make_pair(
    completer: Any,
    question: str,
    excerpts: Sequence[Any],
    variant: tuple[str, str, StyleRule, StyleRule],
) -> tuple[str, str] | None:
    """Generate two answers under contrasting style rules, requiring valid citations for both."""
    from techradar.llm.client import complete_json
    from techradar.llm.roles import Role
    from techradar.profile.style import render_profile_block

    var_a_name, var_b_name, rule_a, rule_b = variant
    excerpts_text = "\n".join(str(e) for e in excerpts)

    system_a = f"You are a helpful tutor.\n{render_profile_block([rule_a])}"
    system_b = f"You are a helpful tutor.\n{render_profile_block([rule_b])}"
    user_prompt = f"Excerpts:\n{excerpts_text}\n\nQuestion: {question}"

    try:
        ans_a = await complete_json(completer, Role.WORKER, system_a, user_prompt, PairAnswer)
        ans_b = await complete_json(completer, Role.WORKER, system_b, user_prompt, PairAnswer)
    except Exception:
        return None

    txt_a = ans_a.text
    txt_b = ans_b.text

    if not _has_valid_citations(txt_a) and not ans_a.citations:
        return None
    if not _has_valid_citations(txt_b) and not ans_b.citations:
        return None

    return txt_a, txt_b


def format_pair_message(
    question: str,
    ans_a: str,
    ans_b: str,
    pair_id: int,
) -> tuple[str, list[list[Button]]]:
    """Format Telegram comparison message and voting inline buttons."""
    text = f"Which is better?\nA: {ans_a}\n\nB: {ans_b}"
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


async def record_pair_choice(
    session: AsyncSession,
    pair_id: int,
    chosen: Literal["a", "b", "skip"],
    now: datetime | None = None,
) -> None:
    """Record user preference choice for an active pair."""
    ts = now or datetime.now(UTC)
    stmt = select(PreferencePair).where(PreferencePair.id == pair_id)
    res = await session.execute(stmt)
    pair = res.scalar_one_or_none()
    if pair:
        pair.chosen = chosen
        pair.answered_at = ts
        await session.flush()
