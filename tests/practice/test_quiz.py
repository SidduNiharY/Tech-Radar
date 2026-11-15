from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from techradar.db.engine import make_engine
from techradar.db.models import MCQ, Flashcard, Mistake, QuizAttempt
from techradar.practice.mistakes import MistakeRow, render_mistakes_page, run_mistakes_page
from techradar.practice.quiz import (
    AnswerOutcome,
    McqRow,
    QuizResult,
    record_answer,
    render_feedback,
    render_mcq,
    run_quiz,
)
from techradar.settings import Settings

NOW = datetime(2026, 11, 8, 10, 0, tzinfo=UTC)

SAMPLE_MCQ = McqRow(
    id=42,
    question="Which organisation publishes the Wholesale Price Index in India?",
    options=[
        "Reserve Bank of India",
        "Office of Economic Adviser",
        "NITI Aayog",
        "Ministry of Finance",
    ],
    answer_index=1,
    explanation="Office of Economic Adviser under DPIIT publishes WPI.",
)


def test_render_mcq_buttons() -> None:
    text_content, kb = render_mcq(SAMPLE_MCQ, 1, 10)
    assert text_content.startswith("Q1/10 · ")
    assert "Which organisation publishes the Wholesale Price Index in India?" in text_content
    assert "A. Reserve Bank of India" in text_content
    assert "B. Office of Economic Adviser" in text_content
    assert [b.data for b in kb[0]] == [f"ans:{SAMPLE_MCQ.id}:{i}" for i in range(4)]
    assert [b.text for b in kb[0]] == ["A", "B", "C", "D"]


def test_render_mcq_indian_languages_pass_through() -> None:
    hindi_q = "भारतीय संविधान की 8वीं अनुसूची में कितनी भाषाएं शामिल हैं?"
    bengali_opt = "২২টি ভাষা (22 languages)"
    tamil_exp = "எட்டாவது அட்டவணையில் 22 மொழிகள் பட்டியலிடப்பட்டுள்ளன."
    mcq = McqRow(
        id=77,
        question=hindi_q,
        options=["14", "18", bengali_opt, "25"],
        answer_index=2,
        explanation=tamil_exp,
    )
    text_content, kb = render_mcq(mcq, 2, 5)
    assert text_content.startswith("Q2/5 · ")
    assert hindi_q in text_content
    assert bengali_opt in text_content
    assert [b.data for b in kb[0]] == [f"ans:{mcq.id}:{i}" for i in range(4)]


def test_render_feedback() -> None:
    options = ["Delhi", "Mumbai", "Kolkata", "Chennai"]
    outcome_correct = AnswerOutcome(
        correct=True,
        correct_index=0,
        explanation="Capital of India.",
        already_answered=False,
    )
    assert render_feedback(outcome_correct, options) == "✅ Correct."

    outcome_wrong = AnswerOutcome(
        correct=False,
        correct_index=1,
        explanation="Financial capital of India.",
        already_answered=False,
    )
    fb = render_feedback(outcome_wrong, options)
    assert fb == "❌ Answer: B. Mumbai — Financial capital of India."


def test_quiz_result_model() -> None:
    qr = QuizResult(questions_sent=5, mcq_ids=[1, 2, 3, 4, 5])
    assert qr.questions_sent == 5
    assert qr.mcq_ids == [1, 2, 3, 4, 5]
    assert qr.skipped_reason is None


def test_render_mistakes_page_empty() -> None:
    md = render_mistakes_page([])
    assert "kind: mistakes" in md
    assert "generated: true" in md
    assert "total: 0" in md
    assert "No recorded mistakes" in md


def test_render_mistakes_page_with_rows() -> None:
    row = MistakeRow(
        id=1,
        kind="mcq",
        ref_id=42,
        detail={
            "question": "What is CRR?",
            "chosen_text": "9%",
            "correct_text": "4%",
            "explanation": "RBI sets CRR to 4%.",
        },
        created_at=NOW,
    )
    md = render_mistakes_page([row])
    assert "kind: mistakes" in md
    assert "generated: true" in md
    assert "total: 1" in md
    assert "# Mistakes Notebook" in md
    assert "### [MCQ] #42" in md
    assert "What is CRR?" in md
    assert "- **Your Answer:** 9%" in md
    assert "- **Correct Answer:** 4%" in md
    assert "RBI sets CRR to 4%." in md


# --- Unit Tests with FakeAsyncSession ---


class FakeAsyncSession:
    """In-memory AsyncSession fake for unit testing without live PostgreSQL."""

    def __init__(self, mcqs: list[MCQ] | None = None) -> None:
        self.mcqs: dict[int, MCQ] = {m.id: m for m in (mcqs or [])}
        self.added: list[Any] = []
        self.attempts: list[QuizAttempt] = []
        self.mistakes: list[Mistake] = []
        self.flashcards: list[Flashcard] = []
        self.flushed = False

    async def get(self, entity: type, ident: Any) -> Any:
        if entity is MCQ:
            return self.mcqs.get(ident)
        for obj in self.added:
            if isinstance(obj, entity) and getattr(obj, "id", None) == ident:
                return obj
        return None

    async def execute(self, stmt: Any) -> Any:
        class FakeResult:
            def __init__(self, items: list[Any]) -> None:
                self._items = items

            def scalars(self) -> FakeResult:
                return self

            def all(self) -> list[Any]:
                return list(self._items)

            def first(self) -> Any | None:
                return self._items[0] if self._items else None

        stmt_str = str(stmt).lower()
        if "quiz_attempts" in stmt_str:
            return FakeResult(self.attempts)
        if "mistakes" in stmt_str:
            return FakeResult(self.mistakes)
        if "mcqs" in stmt_str:
            return FakeResult(list(self.mcqs.values()))
        return FakeResult([])

    def add(self, obj: Any) -> None:
        self.added.append(obj)
        if isinstance(obj, QuizAttempt):
            self.attempts.append(obj)
        elif isinstance(obj, Mistake):
            self.mistakes.append(obj)
        elif isinstance(obj, Flashcard):
            self.flashcards.append(obj)

    async def flush(self) -> None:
        self.flushed = True


@pytest.mark.asyncio
async def test_record_answer_unit_correct() -> None:
    mcq = MCQ(
        id=1,
        question="What is the SI unit of force?",
        options=["Newton", "Joule", "Pascal", "Watt"],
        answer_index=0,
        explanation="Newton (N) is kg*m/s^2.",
        status="active",
    )
    session = FakeAsyncSession(mcqs=[mcq])
    outcome = await record_answer(session, mcq.id, chosen=0, now=NOW)
    assert outcome.correct is True
    assert outcome.correct_index == 0
    assert outcome.already_answered is False
    assert len(session.attempts) == 1
    assert len(session.mistakes) == 0
    assert len(session.flashcards) == 0


@pytest.mark.asyncio
async def test_record_answer_unit_wrong_creates_mistake_and_card() -> None:
    mcq = MCQ(
        id=2,
        question="Which planet is known as the Red Planet?",
        options=["Venus", "Jupiter", "Mars", "Saturn"],
        answer_index=2,
        explanation="Mars appears red due to iron oxide on its surface.",
        status="active",
    )
    session = FakeAsyncSession(mcqs=[mcq])
    outcome = await record_answer(session, mcq.id, chosen=0, now=NOW)
    assert outcome.correct is False
    assert outcome.correct_index == 2
    assert outcome.already_answered is False
    assert len(session.attempts) == 1
    assert len(session.mistakes) == 1
    assert len(session.flashcards) == 1

    mistake = session.mistakes[0]
    assert mistake.kind == "mcq"
    assert mistake.ref_id == 2
    assert mistake.detail["chosen_text"] == "Venus"
    assert mistake.detail["correct_text"] == "Mars"

    card = session.flashcards[0]
    assert card.source_kind == "mcq"
    assert card.source_id == 2
    assert card.front == mcq.question
    assert "Mars" in card.back


@pytest.mark.asyncio
async def test_record_answer_unit_idempotent() -> None:
    mcq = MCQ(
        id=3,
        question="Speed of light in vacuum?",
        options=["3e8 m/s", "3e6 m/s", "3e5 km/h", "Infinite"],
        answer_index=0,
        explanation="c = 299,792,458 m/s.",
        status="active",
    )
    session = FakeAsyncSession(mcqs=[mcq])
    o1 = await record_answer(session, mcq.id, chosen=0, now=NOW)
    assert o1.already_answered is False

    # Second answer on the same date
    o2 = await record_answer(session, mcq.id, chosen=1, now=NOW)
    assert o2.already_answered is True
    assert o2.correct is True  # preserved from first attempt
    assert len(session.attempts) == 1


@pytest.mark.asyncio
async def test_run_quiz_unit() -> None:
    mcq1 = MCQ(
        id=10,
        question="Q1",
        options=["A", "B", "C", "D"],
        answer_index=0,
        explanation="Exp 1",
        status="active",
    )
    mcq2 = MCQ(
        id=11,
        question="Q2",
        options=["A", "B", "C", "D"],
        answer_index=1,
        explanation="Exp 2",
        status="active",
    )
    session = FakeAsyncSession(mcqs=[mcq1, mcq2])
    res = await run_quiz(session, now=NOW, owner_chat_id=123, limit=10)
    assert res.questions_sent == 2
    assert res.mcq_ids == [10, 11]
    assert len(session.added) >= 2


@pytest.mark.asyncio
async def test_run_mistakes_page_unit(tmp_path: Path) -> None:
    session = FakeAsyncSession()
    session.mistakes.append(
        Mistake(
            id=1,
            kind="mcq",
            ref_id=10,
            detail={
                "question": "What is RAM?",
                "chosen_text": "Read Access",
                "correct_text": "Random Access",
            },
            created_at=NOW,
        )
    )
    res = await run_mistakes_page(session, now=NOW, vault_dir=tmp_path)
    assert res.mistakes_count == 1
    assert res.page_path == "practice/mistakes.md"
    assert (tmp_path / "practice/mistakes.md").is_file()
    content = (tmp_path / "practice/mistakes.md").read_text(encoding="utf-8")
    assert "generated: true" in content
    assert "What is RAM?" in content


# --- Database Integration Tests (@pytest.mark.db) ---


TABLE_MODELS: dict[str, type] = {
    "mistakes": Mistake,
    "flashcards": Flashcard,
    "quiz_attempts": QuizAttempt,
    "mcqs": MCQ,
}


async def count(session: AsyncSession, table_name: str) -> int:
    model = TABLE_MODELS[table_name]
    res = await session.scalar(func.count(model.id))
    return int(res or 0)


@pytest.fixture
def db_settings() -> Settings:
    return Settings(
        telegram_owner_chat_id=1,
        db_host="127.0.0.1",
        db_port=55432,
        db_name="techradar",
        secrets_dir=Path("secrets"),
    )


@pytest.fixture
async def session(db_settings: Settings) -> AsyncGenerator[AsyncSession]:
    engine = make_engine("app", db_settings)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s
        await s.rollback()
    await engine.dispose()


@pytest.mark.db
async def test_wrong_answer_creates_mistake_and_card(session: AsyncSession) -> None:
    mcq = MCQ(
        question="Which organisation publishes the Wholesale Price Index in India?",
        options=[
            "Reserve Bank of India",
            "Office of Economic Adviser",
            "NITI Aayog",
            "Ministry of Finance",
        ],
        answer_index=1,
        explanation="Office of Economic Adviser under DPIIT publishes WPI.",
        status="active",
    )
    session.add(mcq)
    await session.flush()

    o = await record_answer(session, mcq.id, chosen=(mcq.answer_index + 1) % 4, now=NOW)
    assert not o.correct
    assert await count(session, "mistakes") == 1
    assert await count(session, "flashcards") == 1


@pytest.mark.db
async def test_quiz_answer_idempotent(session: AsyncSession) -> None:
    mcq = MCQ(
        question=(
            "Which schedule of the Indian Constitution contains the list of recognized languages?"
        ),
        options=["Seventh", "Eighth", "Ninth", "Tenth"],
        answer_index=1,
        explanation="Eighth Schedule contains 22 recognized languages.",
        status="active",
    )
    session.add(mcq)
    await session.flush()

    await record_answer(session, mcq.id, 0, NOW)
    assert (await record_answer(session, mcq.id, 1, NOW)).already_answered
