"""Quiz skill, start side: read the first question. The running state goes back to the caller
(`SkillReply.quiz`); storing it and recording answers are writes and belong to the turn code."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import MCQ, QuizAttempt
from techradar.jarvis.skill_impl.result import SkillReply
from techradar.practice.flashcards import due_cards

LETTERS = "ABCD"


def read_mcq(question: str, options: list[str]) -> str:
    opts = " ".join(f"{LETTERS[i]}: {o}." for i, o in enumerate(options[:4]))
    return f"{question} {opts}"


async def run(
    session: AsyncSession, now: datetime, *, kind: str = "mcq", count: int = 10
) -> SkillReply:
    count = max(1, min(count, 20))
    if kind == "mcq":
        answered_today = select(QuizAttempt.mcq_id).where(QuizAttempt.date == now.date())
        rows = (
            (
                await session.execute(
                    select(MCQ)
                    .where(MCQ.status == "active", MCQ.id.not_in(answered_today))
                    .order_by(MCQ.id)
                    .limit(count)
                )
            )
            .scalars()
            .all()
        )
        if not rows:
            return SkillReply(say="There are no quiz questions waiting today.")
        first = rows[0]
        return SkillReply(
            say=f"Question 1 of {len(rows)}. {read_mcq(first.question, list(first.options))}",
            quiz={"kind": "mcq", "ids": [r.id for r in rows], "index": 0},
        )
    if kind == "cards":
        cards = (await due_cards(session, now))[:count]
        if not cards:
            return SkillReply(say="No flashcards are due right now.")
        return SkillReply(
            say=f"Card 1 of {len(cards)}. {cards[0].front}",
            quiz={"kind": "cards", "ids": [c.id for c in cards], "index": 0},
        )
    raise ValueError(f"unknown quiz kind: {kind!r}")
