from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import GrammarItem as DBGrammarItem
from techradar.db.models import Mistake
from techradar.llm.client import Completer, complete_json
from techradar.llm.roles import Role
from techradar.messaging.outbox import Button, enqueue_message

logger = logging.getLogger(__name__)

_LINK_RE = re.compile(r"(?i)(https?://|www\.|\]\(|!\[|<\s*(a|img|script|iframe)\b|data:)")


def _contains_link(text: str) -> bool:
    """Returns True if the text contains URLs or link markdown/HTML patterns."""
    return bool(_LINK_RE.search(text))


def reject_links(value: str) -> str:
    """Rejects strings that contain link markdown, HTML or URLs (SEC-20)."""
    if _LINK_RE.search(value):
        raise ValueError("links are not allowed")
    return value


NoLinks = Annotated[str, AfterValidator(reject_links)]


class GrammarRule(StrEnum):
    """Grammar rules evaluated in daily practice sets."""

    TENSE = "tense"
    ARTICLES = "articles"
    PREPOSITIONS = "prepositions"
    SUBJECT_VERB = "subject_verb"
    PRONOUNS = "pronouns"
    MODIFIERS = "modifiers"
    CONJUNCTIONS = "conjunctions"
    PARALLELISM = "parallelism"
    VOICE = "voice"
    NARRATION = "narration"

    @classmethod
    def _missing_(cls, value: object) -> GrammarRule | None:
        if isinstance(value, str):
            val_lower = value.lower()
            for member in cls:
                if member.value == val_lower or member.name.lower() == val_lower:
                    return member
        return None


class GrammarItem(BaseModel):
    """Checked grammar practice item verified by two independent models."""

    kind: Literal["error_spotting", "sentence_improvement", "fill_blank"]
    prompt: Annotated[
        str,
        Field(min_length=10, max_length=300),
        AfterValidator(reject_links),
    ]
    options: list[
        Annotated[
            str,
            Field(min_length=1, max_length=120),
            AfterValidator(reject_links),
        ]
    ]
    answer_index: Annotated[int, Field(ge=0, le=3)]
    rule: GrammarRule
    explanation: Annotated[
        str,
        Field(max_length=400),
        AfterValidator(reject_links),
    ] = ""

    @field_validator("options")
    @classmethod
    def validate_options(cls, v: list[str]) -> list[str]:
        if len(v) != 4:
            raise ValueError("options must contain exactly 4 items")
        if len(set(v)) != 4:
            raise ValueError("options must be unique")
        return v

    @field_validator("answer_index")
    @classmethod
    def validate_answer_index(cls, v: int) -> int:
        if v < 0 or v > 3:
            raise ValueError("answer_index must be between 0 and 3")
        return v


class _GrammarCheckerAnswer(BaseModel):
    answer_index: int


async def make_grammar_item(
    completer: Completer,
    rule: GrammarRule,
    kind: str,
) -> GrammarItem | None:
    """Worker model writes grammar question; checker model verifies answer_index.

    Returns None on checker disagreement, schema violation, or generation error.
    """
    rule_enum = GrammarRule(rule) if isinstance(rule, str) else rule

    worker_system = (
        "You are an English exam question creator for competitive exams (GATE, SSC, Bank PO). "
        f"Generate a '{kind}' grammar question testing the rule '{rule_enum.value}'. "
        "Provide exactly 4 unique options, a 0-based answer_index (0 to 3), and an explanation. "
        "Do not include any URLs, web addresses, or markdown links."
    )
    worker_user = (
        f"Create a single '{kind}' grammar question testing rule: {rule_enum.value}.\n"
        "Ensure prompt is between 10 and 300 characters, options are exactly 4 unique choices, "
        "and explanation is concise."
    )

    try:
        item = await complete_json(
            completer,
            Role.WORKER,
            worker_system,
            worker_user,
            GrammarItem,
            attempts=1,
        )
    except Exception as exc:
        logger.debug("Worker failed to generate grammar item: %s", exc)
        return None

    # Checker verifies the answer independently
    options_text = "\n".join(f"{idx}: {opt}" for idx, opt in enumerate(item.options))
    checker_system = (
        "You are an independent English grammar checker. "
        "Analyze the provided question and options, and return the index (0, 1, 2, or 3) "
        "of the correct answer."
    )
    checker_user = (
        f"Question Prompt:\n{item.prompt}\n\n"
        f"Options:\n{options_text}\n\n"
        f"Target Rule: {item.rule.value}\n\n"
        "Return the 0-based index of the correct option as JSON: {'answer_index': <int>}."
    )

    try:
        checker_ans = await complete_json(
            completer,
            Role.CHECKER,
            checker_system,
            checker_user,
            _GrammarCheckerAnswer,
            attempts=1,
        )
    except Exception as exc:
        logger.debug("Checker failed to verify grammar item: %s", exc)
        return None

    if checker_ans.answer_index != item.answer_index:
        logger.info(
            "Grammar checker disagreed: worker=%d, checker=%d",
            item.answer_index,
            checker_ans.answer_index,
        )
        return None

    return item


class GrammarResult(BaseModel):
    """Result of running daily grammar job."""

    items_created: int = 0
    items: list[GrammarItem] = Field(default_factory=list)
    skipped_reason: str | None = None


async def run_grammar(
    session: AsyncSession,
    completer: Completer,
    *,
    now: datetime,
    limit: int = 10,
) -> GrammarResult:
    """Body of grammar_job. Generates verified grammar questions and persists to database."""
    created_items: list[GrammarItem] = []
    rules = list(GrammarRule)
    kinds: list[Literal["error_spotting", "sentence_improvement", "fill_blank"]] = [
        "fill_blank",
        "sentence_improvement",
        "error_spotting",
    ]

    rule_idx = 0
    kind_idx = 0
    attempts = 0
    max_attempts = limit * 4

    while len(created_items) < limit and attempts < max_attempts:
        rule = rules[rule_idx % len(rules)]
        kind = kinds[kind_idx % len(kinds)]
        rule_idx += 1
        kind_idx += 1
        attempts += 1

        try:
            item = await make_grammar_item(completer, rule, kind)
        except Exception as exc:
            logger.debug("Grammar item creation attempt encountered error: %s", exc)
            item = None

        if item is not None:
            created_items.append(item)
            db_item = DBGrammarItem(
                kind=item.kind,
                prompt=item.prompt,
                options=item.options,
                answer_index=item.answer_index,
                rule=str(item.rule.value if isinstance(item.rule, GrammarRule) else item.rule),
                explanation=item.explanation,
                created_at=now,
            )
            session.add(db_item)

    if created_items:
        await session.flush()

    return GrammarResult(
        items_created=len(created_items),
        items=created_items,
        skipped_reason="no_agreed_items" if not created_items else None,
    )


LETTERS = ("A", "B", "C", "D")


def render_grammar_item(
    item_id: int, prompt: str, options: Sequence[str], n: int, total: int
) -> tuple[str, list[list[Button]]]:
    """`G<n>/<total> · <prompt>`, the options, and A-D buttons `gram:<item_id>:<0-3>`."""
    lines = [f"G{n}/{total} · {prompt}", ""]
    lines += [f"{LETTERS[i]}. {opt}" for i, opt in enumerate(options)]
    buttons = [[Button(text=LETTERS[i], data=f"gram:{item_id}:{i}") for i in range(len(options))]]
    return "\n".join(lines), buttons


async def run_grammar_set(
    session: AsyncSession, *, now: datetime, owner_chat_id: int, limit: int = 10
) -> int:
    """Job body for `/grammar`: the newest `limit` checked items, each with its buttons."""
    rows = (
        (
            await session.execute(
                select(DBGrammarItem).order_by(DBGrammarItem.id.desc()).limit(limit)
            )
        )
        .scalars()
        .all()
    )
    for n, row in enumerate(rows, 1):
        text, buttons = render_grammar_item(row.id, row.prompt, row.options, n, len(rows))
        await enqueue_message(
            session,
            chat_id=owner_chat_id,
            text=text,
            buttons=buttons,
            purpose="grammar",
            ref_id=row.id,
        )
    return len(rows)


async def answer_grammar(
    session: AsyncSession, item_id: int, chosen: int, now: datetime
) -> str | None:
    """Feedback text for one answer; a wrong one is noted once a day in the mistakes notebook."""
    item = await session.get(DBGrammarItem, item_id)
    if item is None or not 0 <= chosen < len(item.options):
        return None
    if chosen == item.answer_index:
        return "✅ Correct."
    letter, key = LETTERS[item.answer_index], item.options[item.answer_index]
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    noted = await session.scalar(
        select(Mistake.id)
        .where(
            Mistake.kind == "grammar",
            Mistake.ref_id == item_id,
            Mistake.created_at >= day_start,
        )
        .limit(1)
    )
    if noted is None:
        session.add(
            Mistake(
                kind="grammar",
                ref_id=item_id,
                detail={
                    "question": item.prompt,
                    "chosen_text": item.options[chosen],
                    "correct_text": key,
                    "explanation": item.explanation,
                },
                created_at=now,
            )
        )
        await session.flush()
    return f"❌ Answer: {letter}. {key} — {item.explanation}"
