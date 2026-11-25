"""The run_* functions behind the English practice jobs (Phase 6 Tasks 7, 8 and 9b).

Each takes a session and `now` (no clock reads, no settings) so it is testable; the thin job
wrappers in `worker/tasks.py` open the session and pass the real models. Every message to the
owner goes through the outbox. Nothing here reads the network: LanguageTool and the models come
in as arguments.

SEC: SEC-15, SEC-17, SEC-18, SEC-26.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import Outbox
from techradar.db.models import WritingFeedback as WritingFeedbackRow
from techradar.english.grammar_check import GrammarChecker, GrammarIssue
from techradar.english.reading import reading_quiz
from techradar.english.reflection import PROMPT_REFLECTION
from techradar.english.writing import (
    WritingFeedback,
    feedback_on_text,
    render_writing_feedback,
    route_and_validate_polish,
)
from techradar.llm.client import Completer
from techradar.messaging.outbox import enqueue_message
from techradar.security.text import sanitize_text

logger = logging.getLogger(__name__)

TIMED_WINDOW = timedelta(minutes=30)
ESSAY_REF = 1  # `ref_id` of an essay prompt; a letter prompt is LETTER_REF
LETTER_REF = 2
DEFAULT_TOPICS = (
    "Should students be allowed to use AI tools in exams?",
    "Describe a problem in your city and how you would fix it.",
    "Is remote work better than office work?",
    "How can technology improve rural education?",
)
LETTER_TOPIC = "Write a formal letter to your manager asking for a change of project."
FEEDBACK_FAILED = "I couldn't check that just now. Try again later."


class SafeGrammarChecker:
    """LanguageTool that never stops feedback: when the container is down, there are no issues."""

    def __init__(self, inner: GrammarChecker) -> None:
        self._inner = inner

    async def check(self, text: str) -> list[GrammarIssue]:
        try:
            return await self._inner.check(text)
        except Exception:
            logger.warning("LanguageTool unavailable; continuing without it", exc_info=True)
            return []


def _critique(fb: WritingFeedback) -> str:
    lines = [f"- {r}" for r in fb.reasons]
    lines += [f"- {i.message}" for i in fb.issues[:5]]
    return "\n".join(lines)


async def _store_feedback(
    session: AsyncSession, kind: str, source_id: int | None, original: str, fb: WritingFeedback
) -> None:
    session.add(
        WritingFeedbackRow(
            source_kind=kind,
            source_id=source_id,
            original_text=original,
            critique=_critique(fb),
            polished_text=fb.improved,
        )
    )


async def run_polish(
    session: AsyncSession,
    text: str,
    *,
    owner_chat_id: int,
    lt: GrammarChecker | None,
    completer: Completer,
) -> str:
    """`/polish <text>`: improve the text, store it, send the feedback. Returns what was sent."""
    cleaned = text.strip()
    refusal = route_and_validate_polish(cleaned) or (
        None if cleaned else "Send /polish followed by your text."
    )
    if refusal is None:
        try:
            fb = await feedback_on_text(
                sanitize_text(cleaned), "polish", lt and SafeGrammarChecker(lt), completer
            )
        except Exception:
            logger.warning("polish failed", exc_info=True)
            refusal = FEEDBACK_FAILED
        else:
            await _store_feedback(session, "polish", None, cleaned, fb)
            reply = render_writing_feedback(fb)
            await enqueue_message(session, owner_chat_id, reply, purpose="polish")
            return reply
    await enqueue_message(session, owner_chat_id, refusal, purpose="polish")
    return refusal


def pick_topic(topics: list[str], today: date) -> str:
    """The week's topic, stable within an ISO week."""
    year, week, _ = today.isocalendar()
    return topics[(year * 53 + week) % len(topics)]


def read_topics(vault_root: Path) -> list[str]:
    """Bullet lines of `practice/essay_topics.md`; the built-in list when the file is absent."""
    path = vault_root / "practice" / "essay_topics.md"
    if path.is_file() and not path.is_symlink():
        lines = [
            ln.lstrip("-* ").strip()
            for ln in path.read_text(encoding="utf-8").splitlines()
            if ln.lstrip().startswith(("-", "*"))
        ]
        topics = [t[:200] for t in lines if t]
        if topics:
            return topics
    return list(DEFAULT_TOPICS)


def prompt_kind(today: date) -> Literal["essay", "letter"]:
    """Essays and letters alternate each ISO week."""
    return "essay" if today.isocalendar().week % 2 == 0 else "letter"


async def run_essay_prompt(
    session: AsyncSession, today: date, *, owner_chat_id: int, vault_root: Path
) -> Literal["essay", "letter"]:
    """Saturday: send the essay or letter prompt (purpose `essay`: a reply to it is checked)."""
    kind = prompt_kind(today)
    if kind == "essay":
        body = f"Weekly essay (150 words): {pick_topic(read_topics(vault_root), today)}"
    else:
        body = f"Weekly letter (120 words): {LETTER_TOPIC}"
    text = f"{body}\nReply within 30 minutes for a timed attempt."
    await enqueue_message(
        session,
        owner_chat_id,
        text,
        purpose="essay",
        ref_id=ESSAY_REF if kind == "essay" else LETTER_REF,
    )
    return kind


async def run_essay_reply(
    session: AsyncSession,
    text: str,
    *,
    ref_id: int,
    timed: bool,
    owner_chat_id: int,
    lt: GrammarChecker | None,
    completer: Completer,
) -> str:
    """Feedback with a rubric for a reply to an essay or letter prompt."""
    kind: Literal["essay", "letter"] = "letter" if ref_id == LETTER_REF else "essay"
    cleaned = sanitize_text(text.strip())[:4000]
    try:
        fb = await feedback_on_text(cleaned, kind, lt and SafeGrammarChecker(lt), completer)
    except Exception:
        logger.warning("essay feedback failed", exc_info=True)
        await enqueue_message(session, owner_chat_id, FEEDBACK_FAILED, purpose="essay_feedback")
        return FEEDBACK_FAILED
    await _store_feedback(session, kind, ref_id, cleaned, fb)
    reply = render_writing_feedback(fb) + ("" if timed else "\n(untimed)")
    await enqueue_message(session, owner_chat_id, reply, purpose="essay_feedback")
    return reply


def is_timed(prompt_sent_at: datetime, replied_at: datetime) -> bool:
    return replied_at - prompt_sent_at <= TIMED_WINDOW


# --- Task 8: reading quiz, reflection prompt --------------------------------------------


async def pick_note(vault_root: Path, today: date) -> tuple[str, str] | None:
    """A note of the last 7 days from `wiki/news/` (relative path, text), or None."""
    root = vault_root / "wiki" / "news"
    if not root.is_dir():
        return None
    notes = sorted(
        (p for p in root.rglob("*.md") if p.is_file() and not p.is_symlink()),
        key=lambda p: p.name,
    )
    if not notes:
        return None
    note = notes[(today.toordinal()) % len(notes)]
    return str(note.relative_to(vault_root)), note.read_text(encoding="utf-8")[:6000]


async def run_reading_quiz(
    session: AsyncSession,
    today: date,
    *,
    owner_chat_id: int,
    vault_root: Path,
    completer: Completer,
) -> int:
    """Friday: five questions from one note, sent as quiz messages. Returns questions sent."""
    picked = await pick_note(vault_root, today)
    if picked is None:
        return 0
    rel, text = picked
    questions = await reading_quiz(text, completer)
    if not questions:
        return 0
    body = "\n\n".join(
        f"{n + 1}. {q.question}\n" + "\n".join(f"{'ABCD'[i]}. {o}" for i, o in enumerate(q.options))
        for n, q in enumerate(questions)
    )
    await enqueue_message(
        session, owner_chat_id, f"Reading quiz from {rel}\n\n{body}", purpose="reading_quiz"
    )
    answers = "\n".join(
        f"{n + 1}. {'ABCD'[q.answer_index]}: {q.explanation}".rstrip(": ")
        for n, q in enumerate(questions)
    )
    await enqueue_message(session, owner_chat_id, f"Answers\n{answers}", purpose="reading_answers")
    return len(questions)


async def run_reflection_prompt(session: AsyncSession, *, owner_chat_id: int) -> int:
    """Sunday: ask the weekly reflection question (purpose `reflection`)."""
    return await enqueue_message(session, owner_chat_id, PROMPT_REFLECTION, purpose="reflection")


async def prompt_sent_at(session: AsyncSession, chat_id: int, message_id: int) -> datetime | None:
    """When the replied-to prompt was sent (the outbox row of that Telegram message)."""
    return (
        await session.execute(
            select(Outbox.sent_at).where(
                Outbox.chat_id == chat_id, Outbox.sent_message_id == message_id
            )
        )
    ).scalar_one_or_none()
