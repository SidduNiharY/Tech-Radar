"""db tests for the summarize job body and the book evals (Phase 2c Task 7)."""

from __future__ import annotations

import json
import os
from collections.abc import AsyncGenerator
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from techradar.db.engine import make_engine
from techradar.db.models import BookEval, Chunk, LibraryChapter, LibraryDoc, Outbox
from techradar.library.evals import make_book_evals
from techradar.library.summaries import render_ready, summarize_doc
from techradar.llm.roles import Role
from techradar.settings import Settings
from tests.fakes import FakeCompleter

pytestmark = pytest.mark.db

OWNER = 1234
SUMMARY = json.dumps(
    {"key_ideas": ["First idea [C1]", "Second idea [C2]", "Third idea [C1]"], "terms": []}
)


def _question(i: int) -> str:
    return json.dumps({"question": f"What does chunk {i} explain?"})


@pytest.fixture
def db_settings() -> Settings:
    return Settings(
        telegram_owner_chat_id=OWNER,
        db_host="127.0.0.1",
        db_port=55432,
        db_name="techradar",
        secrets_dir=Path("secrets"),
    )


@pytest.fixture
async def session(db_settings: Settings) -> AsyncGenerator[AsyncSession]:
    """A session whose changes are rolled back after the test."""
    engine = make_engine("app", db_settings)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s
        await s.rollback()
    await engine.dispose()


def _chunk(doc: LibraryDoc, chapter: LibraryChapter, i: int, *, flagged: bool = False) -> Chunk:
    return Chunk(
        doc_path=f"library/{doc.id}/{chapter.ordinal:02d}.md",
        doc_kind="library",
        title=doc.title,
        ordinal=chapter.ordinal * 100 + i,
        text=f"chunk {chapter.ordinal}.{i} text, F = ma",
        lang="en",
        content_hash=os.urandom(32).hex(),
        doc_id=doc.id,
        chapter_id=chapter.id,
        page=chapter.ordinal * 10 + i,
        flagged=flagged,
    )


async def _make_doc(
    session: AsyncSession, n_chapters: int, *, chunks_per: int = 4, status: str = "processing"
) -> SimpleNamespace:
    sha = os.urandom(32).hex()
    doc = LibraryDoc(
        sha256=sha,
        title="A Book",
        kind="pdf",
        origin="library",
        original_path=f"originals/{sha}.pdf",
        size_bytes=10,
        status=status,
        trust="open",
    )
    session.add(doc)
    await session.flush()
    chapters: list[LibraryChapter] = []
    chunks: list[Chunk] = []
    for o in range(1, n_chapters + 1):
        ch = LibraryChapter(
            doc_id=doc.id,
            ordinal=o,
            title=f"Chapter {o}",
            page_start=o * 10,
            page_end=o * 10 + 9,
            text_path=f"text/{doc.id}/{o:02d}.md",
        )
        session.add(ch)
        await session.flush()
        chapters.append(ch)
        for i in range(1, chunks_per + 1):
            c = _chunk(doc, ch, i, flagged=(o == 1 and i == 4))
            session.add(c)
            chunks.append(c)
    await session.flush()
    return SimpleNamespace(doc=doc, chapters=chapters, chunks=chunks)


@pytest.fixture
async def indexed_doc(session: AsyncSession) -> SimpleNamespace:
    """A `processing` doc with 3 chapters of 4 chunks each; one chunk of chapter 1 is flagged."""
    return await _make_doc(session, 3)


async def _run(
    session: AsyncSession, fake: FakeCompleter, d: SimpleNamespace, tmp_path: Path
) -> dict[str, int]:
    return await summarize_doc(
        session,
        fake,
        d.doc.id,
        vault_root=tmp_path / "vault",
        library_dir=tmp_path / "library",
        owner_chat_id=OWNER,
        commit=False,
    )


async def _ready_messages(session: AsyncSession, doc_id: int) -> list[Outbox]:
    rows = await session.execute(
        select(Outbox).where(Outbox.purpose == "library_ready", Outbox.ref_id == doc_id)
    )
    return list(rows.scalars())


# --- book evals ---------------------------------------------------------------------


async def test_book_evals_point_at_their_chunks(session: AsyncSession, indexed_doc):
    unflagged = [c for c in indexed_doc.chunks if not c.flagged]
    fake = FakeCompleter([_question(i) for i in range(15)])
    stored = await make_book_evals(fake, session, indexed_doc.doc.id, n=6)
    assert stored == 6
    assert all(call["role"] == Role.WORKER for call in fake.calls)
    rows = list(
        (
            await session.execute(
                select(BookEval).where(BookEval.doc_id == indexed_doc.doc.id).order_by(BookEval.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 6
    by_id = {c.id: c for c in unflagged}
    for row in rows:
        assert len(row.expected_chunk_ids) == 1
        assert row.expected_chunk_ids[0] in by_id  # an unflagged chunk of this doc
    chapters = {by_id[r.expected_chunk_ids[0]].chapter_id for r in rows}
    assert len(chapters) == 3  # spread over all chapters
    # each prompt carried exactly the chunk it is stored against
    for call, row in zip(fake.calls, rows, strict=True):
        assert by_id[row.expected_chunk_ids[0]].text in call["messages"][1]["content"]


async def test_book_evals_are_idempotent(session: AsyncSession, indexed_doc):
    fake = FakeCompleter([_question(i) for i in range(20)])
    assert await make_book_evals(fake, session, indexed_doc.doc.id, n=4) == 4
    calls = len(fake.calls)
    assert await make_book_evals(fake, session, indexed_doc.doc.id, n=4) == 0
    assert len(fake.calls) == calls


async def test_book_evals_skip_chunks_without_a_valid_question(session: AsyncSession, indexed_doc):
    bad = json.dumps({"question": "see https://evil.example"})
    fake = FakeCompleter([bad, bad, _question(1), _question(2), _question(3)])
    assert await make_book_evals(fake, session, indexed_doc.doc.id, n=3) == 2


# --- the job body -------------------------------------------------------------------


async def test_ready_message_sent_once_and_doc_ready(
    session: AsyncSession, indexed_doc, tmp_path: Path
):
    # 3 chapter summaries, then one question for each of the 11 unflagged chunks
    fake = FakeCompleter([SUMMARY] * 3 + [_question(i) for i in range(15)])
    first = await _run(session, fake, indexed_doc, tmp_path)
    assert first == {"summarized": 3, "failed": 0, "skipped": 0}
    n_calls = len(fake.calls)
    second = await _run(session, fake, indexed_doc, tmp_path)  # a re-run: no model calls
    assert second == {"summarized": 0, "failed": 0, "skipped": 3}
    assert len(fake.calls) == n_calls

    doc = await session.get(LibraryDoc, indexed_doc.doc.id)
    assert doc is not None
    assert doc.status == "ready" and doc.ready_at is not None
    [msg] = await _ready_messages(session, doc.id)
    assert msg.chat_id == OWNER
    assert msg.text == render_ready("A Book", 3)
    assert msg.buttons == [[{"text": "Chapters", "data": f"chap:{doc.id}"}]]

    for ch in indexed_doc.chapters:
        assert ch.summary_path == (
            f"library/a-book-{doc.id}/{ch.ordinal:02d}-chapter-{ch.ordinal}.md"
        )
        note = (tmp_path / "vault" / ch.summary_path).read_text(encoding="utf-8")
        assert "kind: chapter_summary" in note and "generated: true" in note
        assert "[C1]" not in note and "(p. " in note
    evals = (
        (await session.execute(select(BookEval).where(BookEval.doc_id == doc.id))).scalars().all()
    )
    assert len(evals) == 11


async def test_flagged_chunk_text_never_sent_and_pages_come_from_sent_chunks(
    session: AsyncSession, indexed_doc, tmp_path: Path
):
    fake = FakeCompleter([SUMMARY] * 3 + [_question(i) for i in range(15)])
    await _run(session, fake, indexed_doc, tmp_path)
    summary_calls = [c for c in fake.calls if c["role"] == Role.NIGHT]
    assert len(summary_calls) == 3
    assert "chunk 1.4 text" not in json.dumps([c["messages"] for c in fake.calls])
    note = (tmp_path / "vault" / indexed_doc.chapters[0].summary_path).read_text(encoding="utf-8")
    assert "(p. 11)" in note  # [C1] of chapter 1 is its first chunk, page 11


async def test_failed_chapter_is_counted_and_left_without_summary(
    session: AsyncSession, indexed_doc, tmp_path: Path
):
    bad = json.dumps({"key_ideas": ["no", "citations", "here"]})
    fake = FakeCompleter([SUMMARY, bad, bad, SUMMARY] + [_question(i) for i in range(15)])
    counts = await _run(session, fake, indexed_doc, tmp_path)
    assert counts == {"summarized": 2, "failed": 1, "skipped": 0}
    assert [c.summary_path is None for c in indexed_doc.chapters] == [False, True, False]
    doc = await session.get(LibraryDoc, indexed_doc.doc.id)
    assert doc is not None and doc.status == "ready"  # every chapter was attempted
    assert len(await _ready_messages(session, doc.id)) == 1


async def test_doc_with_no_chapters_is_not_made_ready(session: AsyncSession, tmp_path: Path):
    d = await _make_doc(session, 0)
    fake = FakeCompleter([])
    assert await _run(session, fake, d, tmp_path) == {"summarized": 0, "failed": 0, "skipped": 0}
    doc = await session.get(LibraryDoc, d.doc.id)
    assert doc is not None and doc.status == "processing"
    assert await _ready_messages(session, d.doc.id) == []


async def test_doc_that_is_not_indexed_yet_waits(session: AsyncSession, tmp_path: Path):
    d = await _make_doc(session, 2, chunks_per=0)
    fake = FakeCompleter([])
    await _run(session, fake, d, tmp_path)
    doc = await session.get(LibraryDoc, d.doc.id)
    assert doc is not None and doc.status == "processing"
    assert fake.calls == []


@pytest.mark.parametrize("status", ["rejected", "quarantined", "failed", "queued"])
async def test_doc_in_another_status_is_left_alone(
    session: AsyncSession, tmp_path: Path, status: str
):
    d = await _make_doc(session, 1, status=status)
    fake = FakeCompleter([])
    await _run(session, fake, d, tmp_path)
    doc = await session.get(LibraryDoc, d.doc.id)
    assert doc is not None and doc.status == status
    assert fake.calls == []


# --- flagged docs -------------------------------------------------------------------


async def test_flagged_doc_is_not_summarised_or_made_ready(session: AsyncSession, tmp_path: Path):
    d = await _make_doc(session, 2)
    # `flagged` on the doc is a newer column: a plain attribute here keeps the test valid
    # whether or not the model has it yet (the code reads it with getattr)
    d.doc.flagged = True
    fake = FakeCompleter([SUMMARY] * 2 + [_question(i) for i in range(15)])
    assert await _run(session, fake, d, tmp_path) == {"summarized": 0, "failed": 0, "skipped": 0}
    assert fake.calls == []
    assert all(ch.summary_path is None for ch in d.chapters)
    doc = await session.get(LibraryDoc, d.doc.id)
    assert doc is not None and doc.status == "processing" and doc.ready_at is None
    assert await _ready_messages(session, d.doc.id) == []
    assert not (tmp_path / "vault").exists()


async def test_book_evals_refuse_a_flagged_doc(session: AsyncSession):
    d = await _make_doc(session, 2)
    d.doc.flagged = True
    fake = FakeCompleter([_question(i) for i in range(15)])
    assert await make_book_evals(fake, session, d.doc.id) == 0
    assert fake.calls == []
    rows = (await session.execute(select(BookEval).where(BookEval.doc_id == d.doc.id))).all()
    assert rows == []
