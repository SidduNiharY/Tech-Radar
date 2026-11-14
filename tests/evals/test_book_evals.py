"""Book evals in `make rag-eval` (Phase 2c Task 7): recall@5 of each book's own questions."""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from evals.rag.book_evals import (
    BookEvalCase,
    book_eval_cases,
    make_retriever,
    recall_at_5,
)
from techradar.db.engine import make_engine
from techradar.db.models import BookEval, LibraryDoc
from techradar.rag.retrieve import Hit
from techradar.settings import Settings


def _case(i: int, expected: list[int], doc_id: int = 1) -> BookEvalCase:
    return BookEvalCase(id=i, doc_id=doc_id, question=f"q{i}", expected_chunk_ids=expected)


async def test_recall_at_5_with_a_fake_retriever():
    ranked = {"q1": [9, 8, 1, 7, 6, 5], "q2": [2, 3, 4], "q3": [1, 2, 3, 4, 5, 6]}
    seen: list[tuple[str, int]] = []

    async def fake(question: str, doc_id: int) -> list[int]:
        seen.append((question, doc_id))
        return ranked[question]

    cases = [_case(1, [1]), _case(2, [99]), _case(3, [6], doc_id=2)]
    # q1: chunk 1 is rank 3 -> 1.0; q2: missing -> 0.0; q3: chunk 6 is rank 6 -> 0.0
    assert await recall_at_5(cases, fake) == pytest.approx(1 / 3)
    assert seen == [("q1", 1), ("q2", 1), ("q3", 2)]


async def test_recall_at_5_without_cases_is_one():
    async def fake(question: str, doc_id: int) -> list[int]:
        raise AssertionError("not called")

    assert await recall_at_5([], fake) == 1.0


def _hit(i: int) -> Hit:
    return Hit(
        chunk_id=i,
        doc_path="p",
        title="t",
        heading_path=[],
        text="x",
        doc_kind="library",
        verified=None,
        generated=False,
        score=0.9,
    )


async def test_retriever_always_scopes_retrieve_to_the_book():
    calls: list[dict] = []

    async def fake_retrieve(question, deps, f=None, *, doc_id=None):
        calls.append({"question": question, "doc_id": doc_id})
        return [_hit(5), _hit(6)]

    assert await make_retriever(SimpleNamespace(), fake_retrieve)("q", 7) == [5, 6]
    assert calls == [{"question": "q", "doc_id": 7}]


async def test_retriever_never_runs_unscoped_when_retrieve_lacks_doc_id():
    async def old_retrieve(question, deps, f=None):
        raise AssertionError("an unscoped search must never run")

    with pytest.raises(TypeError):
        await make_retriever(SimpleNamespace(), old_retrieve)("q", 7)


# --- reading the cases (db) ---------------------------------------------------------


@pytest.fixture
async def session() -> AsyncGenerator[AsyncSession]:
    settings = Settings(
        telegram_owner_chat_id=1,
        db_host="127.0.0.1",
        db_port=55432,
        db_name="techradar",
        secrets_dir=Path("secrets"),
    )
    engine = make_engine("app", settings)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s
        await s.rollback()
    await engine.dispose()


@pytest.mark.db
async def test_book_eval_cases_read_the_stored_questions(session: AsyncSession):
    sha = os.urandom(32).hex()
    doc = LibraryDoc(
        sha256=sha,
        title="B",
        kind="pdf",
        origin="library",
        original_path=f"originals/{sha}.pdf",
        size_bytes=1,
        status="ready",
        trust="open",
    )
    session.add(doc)
    await session.flush()
    session.add_all(
        [
            BookEval(doc_id=doc.id, question="What is heat?", expected_chunk_ids=[11]),
            BookEval(doc_id=doc.id, question="What is work?", expected_chunk_ids=[12]),
        ]
    )
    await session.flush()
    cases = [c for c in await book_eval_cases(session) if c.doc_id == doc.id]
    assert [(c.question, c.expected_chunk_ids) for c in cases] == [
        ("What is heat?", [11]),
        ("What is work?", [12]),
    ]
