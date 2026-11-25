"""Question answering for the `ask` and `ask_night` jobs (Phase 2c Task 8).

`run_ask` answers with the worker model. A hard question (the answer was refused twice, or no
note scored just under the cut-off) is not answered badly: it is deferred to `ask_night`, which
answers inside the night window with the bigger model and the same checks. Only the owner's
chat gets that deferral; a study group gets the plain result.

Everything a job gets is checked here: the text is bounded, the doc id is a real bounded int.
The night job takes no chat id: it always answers to the owner chat from settings.

SEC: SEC-26, SEC-37, SEC-38, SEC-41.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from techradar.bot.book_ask import valid_id
from techradar.bot.render import render_answer
from techradar.db.models import Answer as AnswerModel
from techradar.feedback.actions import note_ask
from techradar.feedback.signals import TargetKind, feedback_buttons
from techradar.llm.roles import Role
from techradar.messaging.outbox import Button, enqueue_message
from techradar.profile.style import build_profile, mode_of_doc
from techradar.rag.answer import LOW_CONFIDENCE, Answer, answer_question
from techradar.rag.retrieve import RagDeps, RetrieveFilters

logger = logging.getLogger(__name__)

DEFER_REPLY = "I'll answer this one tonight with the bigger model."
PENDING = "pending"  # an answers row the API created for a web ask
DeferNight = Callable[[str, int | None], Awaitable[None]]


def valid_ask_args(question: object, doc_id: object, max_chars: int) -> bool:
    """A non-empty question within `max_chars`, and no book or a real bounded book id."""
    if not isinstance(question, str) or not question.strip() or len(question) > max_chars:
        return False
    return doc_id is None or valid_id(doc_id)


def is_hard(answer: Answer) -> bool:
    """Refused for a reason a bigger model may fix, or an answer that was almost found."""
    if answer.status == "needs_review":
        return "too_long" not in answer.flags  # a too-long question stays too long
    return answer.status == "not_found" and LOW_CONFIDENCE in answer.flags


def _scope(doc_id: int | None) -> dict[str, Any]:
    return {"doc_id": doc_id, "require_doc_id": doc_id is not None}


async def _profile_for(
    session_factory: async_sessionmaker[AsyncSession], question: str, doc_id: int | None
) -> tuple[str | None, str | None]:
    """(profile block, mode) for the owner's question. Never blocks an answer (Phase 11)."""
    try:
        async with session_factory() as session:
            mode = await mode_of_doc(session, doc_id)
            return await build_profile(session, question, mode), mode.value
    except Exception:
        logger.exception("could not build the profile block; answering without it")
        return None, None


async def _deliver(
    session_factory: async_sessionmaker[AsyncSession],
    chat_id: int,
    question: str,
    answer: Answer,
) -> None:
    """Store the answer and queue it. The text is the checked answer, rendered, never raw."""
    async with session_factory() as session:
        row = AnswerModel(
            chat_id=chat_id,
            question=question,
            text=answer.text,
            citations=[c.model_dump() for c in answer.citations],
            status=answer.status,
            used_unverified=answer.used_unverified,
            flags=answer.flags,
        )
        session.add(row)
        await session.flush()
        buttons = None
        if answer.status == "answered":
            buttons = [
                [Button(text="Save to vault", data=f"save_answer:{row.id}")],
                *feedback_buttons(TargetKind.ANSWER, row.id),  # --- Phase 11 ---
            ]
        await enqueue_message(
            session,
            chat_id=chat_id,
            text=render_answer(answer),
            purpose="answer",
            buttons=buttons,
            ref_id=row.id,
        )
        await session.commit()


async def run_ask(
    question: str,
    *,
    chat_id: int,
    doc_id: int | None,
    deps: RagDeps,
    session_factory: async_sessionmaker[AsyncSession],
    owner_chat_id: int,
    defer_night: DeferNight,
) -> None:
    """Answer one question (of one book when `doc_id` is set), or defer it to the night model."""
    if not valid_ask_args(question, doc_id, deps.settings.max_question_chars):
        logger.warning("ask job dropped: invalid arguments")
        return
    scope = _scope(doc_id)
    profile: str | None = None
    if chat_id == owner_chat_id:
        # --- Phase 11: my preferences shape the owner's answers only, never a study group's;
        # the ask is logged (a follow-up within 10 minutes of my last answer is noted) ---
        profile, mode = await _profile_for(session_factory, question, doc_id)
        async with session_factory() as session:
            await note_ask(
                session, chat_id=chat_id, question=question, mode=mode, now=datetime.now(UTC)
            )
            await session.commit()
    answer = await answer_question(question, deps, **scope, profile=profile)
    if answer.status == "needs_review" and "too_long" not in answer.flags:
        # one more try, searching with rewritten queries and the neighbouring chunks
        answer = await answer_question(
            question, deps, **scope, rewrite=True, expand=True, profile=profile
        )
    if chat_id == owner_chat_id and is_hard(answer):
        try:
            await defer_night(question, doc_id)
        except Exception:
            logger.exception("could not defer the night answer; sending the plain result")
        else:
            async with session_factory() as session:
                await enqueue_message(
                    session, chat_id=chat_id, text=DEFER_REPLY, purpose="answer_deferred"
                )
                await session.commit()
            return
    await _deliver(session_factory, chat_id, question, answer)


async def run_web_ask(
    question: str,
    *,
    answer_id: object,
    doc_id: int | None,
    verified_only: bool,
    deps: RagDeps,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Answer a question asked on the web: fill in the `pending` row the API created.

    Phase 4 Task 2. The row must exist, still be pending and hold this question; the write is
    conditional on `status = 'pending'`, so a replayed job never changes a finished answer.
    No outbox message (the web polls) and no night deferral (the web waits up to 120 s).
    On an error the row becomes `needs_review` with the flag `error`, and the error is raised.
    """
    if not valid_ask_args(question, doc_id, deps.settings.max_question_chars):
        logger.warning("web ask job dropped: invalid arguments")
        return
    if not valid_id(answer_id):
        logger.warning("web ask job dropped: invalid answer id")
        return
    row_id = int(answer_id)  # type: ignore[call-overload]
    async with session_factory() as session:
        row = (
            await session.execute(
                select(AnswerModel).where(AnswerModel.id == row_id, AnswerModel.status == PENDING)
            )
        ).scalar_one_or_none()
    if row is None or row.question != question:
        logger.warning("web ask job dropped: no matching pending answer")
        return
    scope = _scope(doc_id)
    f = RetrieveFilters(verified_only=True) if verified_only else None
    try:
        profile = (await _profile_for(session_factory, question, doc_id))[0]  # Phase 11
        answer = await answer_question(question, deps, f=f, **scope, profile=profile)
        if answer.status == "needs_review" and "too_long" not in answer.flags:
            answer = await answer_question(
                question, deps, f=f, **scope, rewrite=True, expand=True, profile=profile
            )
    except Exception:
        await _fill_web_answer(session_factory, row_id, None)
        raise
    await _fill_web_answer(session_factory, row_id, answer)


async def _fill_web_answer(
    session_factory: async_sessionmaker[AsyncSession], row_id: int, answer: Answer | None
) -> None:
    values: dict[str, Any] = (
        {"text": "", "citations": [], "status": "needs_review", "used_unverified": False,
         "flags": ["error"]}
        if answer is None
        else {
            "text": answer.text,
            "citations": [c.model_dump() for c in answer.citations],
            "status": answer.status,
            "used_unverified": answer.used_unverified,
            "flags": answer.flags,
        }
    )  # fmt: skip
    async with session_factory() as session:
        await session.execute(
            update(AnswerModel)
            .where(AnswerModel.id == row_id, AnswerModel.status == PENDING)
            .values(**values)
        )
        await session.commit()


async def run_night_ask(
    question: str,
    *,
    doc_id: int | None,
    deps: RagDeps,
    session_factory: async_sessionmaker[AsyncSession],
    owner_chat_id: int,
) -> None:
    """Answer a deferred question with the night model; the result goes to the owner chat."""
    if not valid_ask_args(question, doc_id, deps.settings.max_question_chars):
        logger.warning("night ask job dropped: invalid arguments")
        return
    profile = (await _profile_for(session_factory, question, doc_id))[0]  # Phase 11
    answer = await answer_question(
        question,
        deps,
        **_scope(doc_id),
        role=Role.NIGHT,
        rewrite=True,
        expand=True,
        profile=profile,
    )
    await _deliver(session_factory, owner_chat_id, question, answer)
