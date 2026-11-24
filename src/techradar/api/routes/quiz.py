"""Today's quiz without answer keys, and answering one question (Phase 3 MCQs).

`GET /v1/quiz/today` selects only id, question and options: the key is never read, so it
cannot leak. The key and explanation come back only in the outcome of an answer.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from techradar.api.deps import AppSession, DbId, Now, RoSession
from techradar.api.schemas import AnswerOutcome, AnswerQuizRequest, QuizQuestion
from techradar.db.models import MCQ
from techradar.practice.quiz import record_answer

router = APIRouter(prefix="/quiz", tags=["quiz"])

QUIZ_SIZE = 10  # as the Telegram quiz (practice.quiz.run_quiz)


def quiz_question(mcq_id: int, question: str, options: Any) -> QuizQuestion | None:
    if not isinstance(options, list) or not 2 <= len(options) <= 4:
        return None
    if not all(isinstance(o, str) for o in options):
        return None
    return QuizQuestion(mcq_id=mcq_id, question=question, options=list(options))


@router.get("/today", response_model=list[QuizQuestion])
async def quiz_today(session: RoSession) -> list[QuizQuestion]:
    rows = (
        await session.execute(
            select(MCQ.id, MCQ.question, MCQ.options)
            .where(MCQ.status == "active")
            .order_by(MCQ.id.desc())
            .limit(QUIZ_SIZE)
        )
    ).all()
    return [q for r in rows if (q := quiz_question(r.id, r.question, r.options)) is not None]


@router.post("/{mcq_id}/answer", response_model=AnswerOutcome)
async def answer_question(
    mcq_id: DbId, body: AnswerQuizRequest, session: AppSession, now: Now
) -> AnswerOutcome:
    mcq = await session.get(MCQ, mcq_id)
    if mcq is None or mcq.status != "active":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    if body.chosen >= len(mcq.options or []):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "No such option")
    outcome = await record_answer(session, mcq_id, body.chosen, now)
    await session.commit()
    return AnswerOutcome.model_validate(outcome.model_dump())
