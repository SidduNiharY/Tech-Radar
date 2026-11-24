from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import MCQ, Flashcard, Mistake, QuizAttempt
from techradar.messaging.outbox import Button, enqueue_message
from techradar.practice.flashcards import new_card_state

LETTERS: list[str] = ["A", "B", "C", "D"]


class McqRow(BaseModel):
    id: int
    question: str
    options: list[str]
    answer_index: int
    explanation: str
    fact_id: int | None = None
    chunk_id: int | None = None
    chapter_id: int | None = None
    status: str = "active"


def render_mcq(m: Any, n: int, total: int) -> tuple[str, list[list[Button]]]:
    """Renders a multiple choice question with formatted text and A-D buttons.

    Text starts with: Q<n>/<total> · <question>
    Buttons: A-D with data ans:<mcq_id>:<0-3>
    """
    options: Sequence[str] = getattr(m, "options", [])
    question: str = getattr(m, "question", "")
    mcq_id: int = getattr(m, "id", 0)

    lines = [f"Q{n}/{total} · {question}\n"]
    for i, opt in enumerate(options):
        letter = LETTERS[i] if i < len(LETTERS) else str(i)
        lines.append(f"{letter}. {opt}")
    text = "\n".join(lines)

    button_count = min(len(LETTERS), len(options)) if options else 4
    buttons = [[Button(text=LETTERS[i], data=f"ans:{mcq_id}:{i}") for i in range(button_count)]]
    return text, buttons


class AnswerOutcome(BaseModel):
    correct: bool
    correct_index: int
    explanation: str
    already_answered: bool


async def record_answer(
    session: AsyncSession,
    mcq_id: int,
    chosen: int,
    now: datetime,
) -> AnswerOutcome:
    """Records a user's answer to an MCQ.

    Idempotent per mcq_id per day. A wrong answer creates a Mistake row
    (kind='mcq') and an FSRS Flashcard.
    """
    today: date = now.date() if hasattr(now, "date") else now

    # Check for existing attempt today (idempotency)
    stmt = select(QuizAttempt).where(
        QuizAttempt.mcq_id == mcq_id,
        QuizAttempt.date == today,
    )
    res = await session.execute(stmt)
    existing = res.scalars().first()

    # Load MCQ record
    mcq = await session.get(MCQ, mcq_id)
    if mcq is None:
        raise ValueError(f"MCQ with id {mcq_id} not found")

    if existing is not None:
        return AnswerOutcome(
            correct=existing.correct,
            correct_index=mcq.answer_index,
            explanation=mcq.explanation,
            already_answered=True,
        )

    is_correct = chosen == mcq.answer_index
    attempt = QuizAttempt(
        mcq_id=mcq_id,
        chosen_index=chosen,
        correct=is_correct,
        answered_at=now,
        date=today,
    )
    session.add(attempt)

    if not is_correct:
        # Create a Mistake row
        chosen_letter = LETTERS[chosen] if 0 <= chosen < len(LETTERS) else str(chosen)
        correct_letter = (
            LETTERS[mcq.answer_index]
            if 0 <= mcq.answer_index < len(LETTERS)
            else str(mcq.answer_index)
        )
        chosen_text = mcq.options[chosen] if 0 <= chosen < len(mcq.options) else str(chosen)
        correct_text = (
            mcq.options[mcq.answer_index]
            if 0 <= mcq.answer_index < len(mcq.options)
            else str(mcq.answer_index)
        )

        mistake = Mistake(
            kind="mcq",
            ref_id=mcq_id,
            detail={
                "question": mcq.question,
                "chosen_index": chosen,
                "chosen_letter": chosen_letter,
                "chosen_text": chosen_text,
                "correct_index": mcq.answer_index,
                "correct_letter": correct_letter,
                "correct_text": correct_text,
                "explanation": mcq.explanation,
            },
            created_at=now,
        )
        session.add(mistake)

        # Create an FSRS Flashcard
        fsrs_card_state, card_due = new_card_state(now)
        back_text = f"{correct_letter}. {correct_text}\n\n{mcq.explanation}"
        flashcard = Flashcard(
            front=mcq.question,
            back=back_text,
            source_kind="mcq",
            source_id=mcq_id,
            fsrs_card=fsrs_card_state,
            due=card_due,
            first_shown_at=None,
            chunk_id=getattr(mcq, "chunk_id", None),
            retired=False,
        )
        session.add(flashcard)

    await session.flush()

    return AnswerOutcome(
        correct=is_correct,
        correct_index=mcq.answer_index,
        explanation=mcq.explanation,
        already_answered=False,
    )


def render_feedback(o: AnswerOutcome, options: list[str]) -> str:
    """Renders user feedback for an answer outcome."""
    if o.correct:
        return "✅ Correct."

    letter = (
        LETTERS[o.correct_index] if 0 <= o.correct_index < len(LETTERS) else str(o.correct_index)
    )
    opt = options[o.correct_index] if 0 <= o.correct_index < len(options) else ""
    return f"❌ Answer: {letter}. {opt} — {o.explanation}"


class QuizResult(BaseModel):
    questions_sent: int = 0
    mcq_ids: list[int] = Field(default_factory=list)
    skipped_reason: str | None = None


async def run_quiz(
    session: AsyncSession,
    *,
    now: datetime,
    owner_chat_id: int,
    limit: int = 10,
) -> QuizResult:
    """Job body for quiz_job: up to `limit` active MCQs to the owner, least answered first."""
    stmt = (
        select(MCQ)
        .outerjoin(QuizAttempt, QuizAttempt.mcq_id == MCQ.id)
        .where(MCQ.status == "active")
        .group_by(MCQ.id)
        .order_by(func.count(QuizAttempt.id).asc(), MCQ.id.asc())
        .limit(limit)
    )
    res = await session.execute(stmt)
    mcqs = list(res.scalars().all())

    if not mcqs:
        return QuizResult(skipped_reason="no_active_mcqs")

    total = len(mcqs)
    mcq_ids: list[int] = []
    for n, m in enumerate(mcqs, 1):
        text, buttons = render_mcq(m, n, total)
        await enqueue_message(
            session,
            chat_id=owner_chat_id,
            text=text,
            buttons=buttons,
            purpose="quiz",
            ref_id=m.id,
        )
        mcq_ids.append(m.id)

    return QuizResult(questions_sent=total, mcq_ids=mcq_ids)
