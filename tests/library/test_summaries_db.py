"""db tests for the summarize job body and the book evals (Phase 2c Task 7)."""

from __future__ import annotations

import json
import os
from collections.abc import AsyncGenerator
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm.exc import StaleDataError

from techradar.db.engine import make_engine
from techradar.db.models import BookEval, Chunk, LibraryChapter, LibraryDoc, Outbox
from techradar.library.evals import make_book_evals
from techradar.library.index import index_library_chapter
from techradar.library.summaries import (
    read_attempts,
    render_ready,
    render_ready_partial,
    summarize_doc,
)
from techradar.llm.roles import Role
from techradar.settings import Settings
from tests.fakes import FakeCompleter, FakeEmbedder

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


BAD = json.dumps({"key_ideas": ["no", "citations", "here"]})


def _counts(**kw: int) -> dict[str, int]:
    base = {"summarized": 0, "failed": 0, "skipped": 0, "given_up": 0, "more": 0}
    base.update(kw)
    return base


async def _run(
    session: AsyncSession, fake: FakeCompleter, d: SimpleNamespace, tmp_path: Path, **kw
) -> dict[str, int]:
    return await summarize_doc(
        session,
        fake,
        d.doc.id,
        vault_root=tmp_path / "vault",
        library_dir=tmp_path / "library",
        owner_chat_id=OWNER,
        commit=False,
        **kw,
    )


def _write_text(tmp_path: Path, chapter: LibraryChapter, text: str) -> None:
    path = tmp_path / "library" / chapter.text_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


async def _drop_chapter(session: AsyncSession, chapter: LibraryChapter) -> None:
    """Delete a chapter and its chunks, as the owner deleting the doc would."""
    await session.execute(delete(Chunk).where(Chunk.chapter_id == chapter.id))
    await session.execute(delete(LibraryChapter).where(LibraryChapter.id == chapter.id))


def _notes(tmp_path: Path) -> list[Path]:
    return sorted((tmp_path / "vault").rglob("*.md")) if (tmp_path / "vault").exists() else []


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
    assert first == _counts(summarized=3)
    n_calls = len(fake.calls)
    second = await _run(session, fake, indexed_doc, tmp_path)  # a re-run: no model calls
    assert second == {"summarized": 0, "failed": 0, "skipped": 3, "given_up": 0, "more": 0}
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


async def test_failed_chapter_keeps_the_doc_processing_and_is_counted(
    session: AsyncSession, indexed_doc, tmp_path: Path
):
    fake = FakeCompleter([SUMMARY, BAD, BAD, SUMMARY] + [_question(i) for i in range(15)])
    counts = await _run(session, fake, indexed_doc, tmp_path)
    assert counts == _counts(summarized=2, failed=1, more=1)
    assert [c.summary_path is None for c in indexed_doc.chapters] == [False, True, False]
    doc = await session.get(LibraryDoc, indexed_doc.doc.id)
    assert doc is not None and doc.status == "processing" and doc.ready_at is None
    assert await _ready_messages(session, doc.id) == []  # not announced with a hole in it
    assert len(fake.calls) == 4  # no evals yet either
    assert read_attempts(tmp_path / "library", indexed_doc.chapters[1].id) == 1
    assert read_attempts(tmp_path / "library", indexed_doc.chapters[0].id) == 0


async def test_all_chapters_failing_never_announces(
    session: AsyncSession, indexed_doc, tmp_path: Path
):
    fake = FakeCompleter([BAD] * 6)
    counts = await _run(session, fake, indexed_doc, tmp_path)
    assert counts == _counts(failed=3, more=1)
    doc = await session.get(LibraryDoc, indexed_doc.doc.id)
    assert doc is not None and doc.status == "processing"
    assert await _ready_messages(session, doc.id) == []


async def test_failed_chapter_is_retried_next_run_and_then_the_doc_is_ready(
    session: AsyncSession, indexed_doc, tmp_path: Path
):
    fake = FakeCompleter([SUMMARY, BAD, BAD, SUMMARY, SUMMARY] + [_question(i) for i in range(15)])
    assert await _run(session, fake, indexed_doc, tmp_path) == _counts(
        summarized=2, failed=1, more=1
    )
    assert await _run(session, fake, indexed_doc, tmp_path) == _counts(summarized=1, skipped=2)
    doc = await session.get(LibraryDoc, indexed_doc.doc.id)
    assert doc is not None and doc.status == "ready" and doc.ready_at is not None
    [msg] = await _ready_messages(session, doc.id)
    assert msg.text == render_ready("A Book", 3)  # all chapters: the exact old message


async def test_chapter_is_given_up_after_three_attempts(
    session: AsyncSession, indexed_doc, tmp_path: Path
):
    third = indexed_doc.chapters[1]
    fake = FakeCompleter(
        [SUMMARY, BAD, BAD, SUMMARY]  # run 1: chapter 2 fails (attempt 1)
        + [BAD, BAD]  # run 2: attempt 2
        + [BAD, BAD]  # run 3: attempt 3, given up
        + [_question(i) for i in range(15)]
    )
    assert (await _run(session, fake, indexed_doc, tmp_path))["more"] == 1
    assert await _run(session, fake, indexed_doc, tmp_path) == _counts(failed=1, skipped=2, more=1)
    doc = await session.get(LibraryDoc, indexed_doc.doc.id)
    assert doc is not None and doc.status == "processing"
    assert read_attempts(tmp_path / "library", third.id) == 2

    assert await _run(session, fake, indexed_doc, tmp_path) == _counts(
        failed=1, skipped=2, given_up=1
    )
    assert read_attempts(tmp_path / "library", third.id) == 3
    assert doc.status == "ready" and doc.ready_at is not None
    [msg] = await _ready_messages(session, doc.id)
    assert msg.text == render_ready_partial("A Book", 2, 3)
    assert third.summary_path is None
    evals = (await session.execute(select(BookEval).where(BookEval.doc_id == doc.id))).all()
    assert evals  # the doc is searchable and has its evals

    calls = len(fake.calls)
    assert await _run(session, fake, indexed_doc, tmp_path) == _counts(skipped=2, given_up=1)
    assert len(fake.calls) == calls  # given up means given up
    assert len(await _ready_messages(session, doc.id)) == 1


async def test_doc_with_no_chapters_is_not_made_ready(session: AsyncSession, tmp_path: Path):
    d = await _make_doc(session, 0)
    fake = FakeCompleter([])
    assert await _run(session, fake, d, tmp_path) == _counts()
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


# --- every chapter must be indexed ---------------------------------------------------


async def test_one_indexed_chapter_is_not_enough(
    session: AsyncSession, indexed_doc, tmp_path: Path
):
    last = indexed_doc.chapters[2]
    await _drop_chapter_chunks(session, last)
    _write_text(tmp_path, last, "Words that the indexer has not embedded yet.")
    fake = FakeCompleter([])
    assert await _run(session, fake, indexed_doc, tmp_path) == _counts()
    assert fake.calls == []
    assert all(c.summary_path is None for c in indexed_doc.chapters)
    doc = await session.get(LibraryDoc, indexed_doc.doc.id)
    assert doc is not None and doc.status == "processing"


async def _drop_chapter_chunks(session: AsyncSession, chapter: LibraryChapter) -> None:
    await session.execute(delete(Chunk).where(Chunk.chapter_id == chapter.id))


@pytest.mark.parametrize("why", ["empty_text", "no_text_file", "all_pages_missing"])
async def test_chapter_with_nothing_to_index_does_not_block_the_doc(
    session: AsyncSession, indexed_doc, tmp_path: Path, why: str
):
    last = indexed_doc.chapters[2]
    await _drop_chapter_chunks(session, last)
    if why == "empty_text":
        _write_text(tmp_path, last, "  \n")
    elif why == "all_pages_missing":
        _write_text(tmp_path, last, "some words")
        last.missing_pages = list(range(last.page_start, last.page_end + 1))
        await session.flush()
    fake = FakeCompleter([SUMMARY] * 2 + [_question(i) for i in range(15)])
    counts = await _run(session, fake, indexed_doc, tmp_path)
    assert counts == _counts(summarized=2, given_up=1)
    doc = await session.get(LibraryDoc, indexed_doc.doc.id)
    assert doc is not None and doc.status == "ready"
    [msg] = await _ready_messages(session, doc.id)
    assert msg.text == render_ready_partial("A Book", 2, 3)
    assert last.summary_path is None


# --- the night window ----------------------------------------------------------------


async def test_run_stops_when_the_window_closes_and_resumes_later(
    session: AsyncSession, indexed_doc, tmp_path: Path
):
    answers = iter([True, False])
    fake = FakeCompleter([SUMMARY] * 3 + [_question(i) for i in range(15)])
    counts = await _run(session, fake, indexed_doc, tmp_path, in_window=lambda: next(answers))
    assert counts == _counts(summarized=1, more=1)  # checked before each chapter
    assert len(fake.calls) == 1
    doc = await session.get(LibraryDoc, indexed_doc.doc.id)
    assert doc is not None and doc.status == "processing"
    assert await _ready_messages(session, doc.id) == []
    assert indexed_doc.chapters[0].summary_path and indexed_doc.chapters[1].summary_path is None

    counts = await _run(session, fake, indexed_doc, tmp_path, in_window=lambda: True)
    assert counts == _counts(summarized=2, skipped=1)
    assert doc.status == "ready"
    assert len(await _ready_messages(session, doc.id)) == 1


async def test_window_closed_at_the_start_makes_no_model_call(
    session: AsyncSession, indexed_doc, tmp_path: Path
):
    fake = FakeCompleter([])
    counts = await _run(session, fake, indexed_doc, tmp_path, in_window=lambda: False)
    assert counts == _counts(more=1)
    assert fake.calls == [] and _notes(tmp_path) == []


# --- deleting a doc while the job runs -------------------------------------------------


class _MidRunCompleter(FakeCompleter):
    """A completer that runs `hook()` (a change made by someone else) during its first call."""

    def __init__(self, responses: list[str], hook) -> None:
        super().__init__(responses)
        self._hook = hook

    async def complete(self, *args, **kwargs):
        if not self.calls:
            await self._hook()
        return await super().complete(*args, **kwargs)


async def test_chapter_deleted_while_summarising_leaves_no_orphan_note(
    session: AsyncSession, indexed_doc, tmp_path: Path
):
    first = indexed_doc.chapters[0]

    async def hook() -> None:
        await _drop_chapter(session, first)

    fake = _MidRunCompleter([SUMMARY] * 3 + [_question(i) for i in range(15)], hook)
    counts = await _run(session, fake, indexed_doc, tmp_path)
    assert counts["summarized"] == 2
    names = [p.name for p in _notes(tmp_path)]
    assert names == ["02-chapter-2.md", "03-chapter-3.md"]  # nothing for the deleted chapter
    doc = await session.get(LibraryDoc, indexed_doc.doc.id)
    assert doc is not None and doc.status == "ready"
    [msg] = await _ready_messages(session, doc.id)
    assert msg.text == render_ready("A Book", 2)  # counts what is still there


async def test_a_failed_flush_removes_the_note_it_wrote(
    session: AsyncSession, indexed_doc, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    async def stale() -> None:
        raise StaleDataError("the row was deleted")

    monkeypatch.setattr(session, "flush", stale)
    fake = FakeCompleter([SUMMARY] * 3)
    counts = await _run(session, fake, indexed_doc, tmp_path)
    assert counts["summarized"] == 0
    assert _notes(tmp_path) == []  # no orphan in the vault


async def test_another_save_error_removes_the_note_and_is_raised(
    session: AsyncSession, indexed_doc, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    async def boom() -> None:
        raise RuntimeError("db went away")

    monkeypatch.setattr(session, "flush", boom)
    fake = FakeCompleter([SUMMARY] * 3)
    with pytest.raises(RuntimeError):
        await _run(session, fake, indexed_doc, tmp_path)
    assert _notes(tmp_path) == []


# --- book evals follow the chunks ------------------------------------------------------


async def test_a_ready_doc_without_evals_gets_them_again(
    session: AsyncSession, indexed_doc, tmp_path: Path
):
    fake = FakeCompleter([SUMMARY] * 3 + [_question(i) for i in range(30)])
    await _run(session, fake, indexed_doc, tmp_path)
    doc_id = indexed_doc.doc.id
    await session.execute(delete(BookEval).where(BookEval.doc_id == doc_id))  # a re-index did this
    assert await _run(session, fake, indexed_doc, tmp_path) == _counts(skipped=3)
    evals = (await session.execute(select(BookEval).where(BookEval.doc_id == doc_id))).all()
    assert len(evals) == 11
    assert len(await _ready_messages(session, doc_id)) == 1  # not announced twice


class _SharedSession:
    """`deps.session_factory()` handing out the test's own session (commit becomes flush)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def __call__(self) -> _SharedSession:
        return self

    async def __aenter__(self) -> AsyncSession:
        return self._session

    async def __aexit__(self, *exc: object) -> None:
        return None


async def test_reindexing_a_chapter_deletes_that_docs_book_evals(
    session: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    d = await _make_doc(session, 1, chunks_per=2)
    other = await _make_doc(session, 1, chunks_per=2)
    for x in (d, other):
        session.add(BookEval(doc_id=x.doc.id, question="Q?", expected_chunk_ids=[x.chunks[0].id]))
    await session.flush()
    monkeypatch.setattr(session, "commit", session.flush)
    chapter = d.chapters[0]
    _write_text(tmp_path, chapter, "# Chapter 1\nSome text about forces.\n")
    deps = SimpleNamespace(
        session_factory=_SharedSession(session),
        embedder=FakeEmbedder(dim=1024),
        library_dir=tmp_path / "library",
    )
    assert await index_library_chapter(deps, chapter.id) > 0
    mine = (await session.execute(select(BookEval).where(BookEval.doc_id == d.doc.id))).all()
    theirs = (await session.execute(select(BookEval).where(BookEval.doc_id == other.doc.id))).all()
    assert mine == []  # their chunk ids no longer exist
    assert len(theirs) == 1  # another book's evals are untouched


async def test_failed_reindex_keeps_the_evals(
    session: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    d = await _make_doc(session, 1, chunks_per=2)
    session.add(BookEval(doc_id=d.doc.id, question="Q?", expected_chunk_ids=[d.chunks[0].id]))
    await session.flush()
    monkeypatch.setattr(session, "commit", session.flush)
    deps = SimpleNamespace(  # no text file: nothing is indexed and the old chunks stay
        session_factory=_SharedSession(session),
        embedder=FakeEmbedder(dim=1024),
        library_dir=tmp_path / "library",
    )
    assert await index_library_chapter(deps, d.chapters[0].id) == 0
    assert (
        len((await session.execute(select(BookEval).where(BookEval.doc_id == d.doc.id))).all()) == 1
    )


# --- flagged docs -------------------------------------------------------------------


async def test_flagged_doc_is_not_summarised_or_made_ready(session: AsyncSession, tmp_path: Path):
    d = await _make_doc(session, 2)
    d.doc.flagged = True
    fake = FakeCompleter([SUMMARY] * 2 + [_question(i) for i in range(15)])
    assert await _run(session, fake, d, tmp_path) == _counts()
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


async def test_flagging_the_doc_mid_run_stops_the_run_and_writes_nothing(
    session: AsyncSession, indexed_doc, tmp_path: Path
):
    async def hook() -> None:
        indexed_doc.doc.flagged = True

    fake = _MidRunCompleter([SUMMARY] * 3 + [_question(i) for i in range(15)], hook)
    counts = await _run(session, fake, indexed_doc, tmp_path)
    assert counts["summarized"] == 0
    assert len(fake.calls) == 1  # stopped after the one call already running
    assert _notes(tmp_path) == []
    assert all(c.summary_path is None for c in indexed_doc.chapters)
    doc = await session.get(LibraryDoc, indexed_doc.doc.id)
    assert doc is not None and doc.status == "processing"
    assert await _ready_messages(session, doc.id) == []


async def test_flagged_doc_loses_the_notes_that_were_already_written(
    session: AsyncSession, indexed_doc, tmp_path: Path
):
    fake = FakeCompleter([SUMMARY] * 3 + [_question(i) for i in range(15)])
    await _run(session, fake, indexed_doc, tmp_path)
    assert len(_notes(tmp_path)) == 3
    indexed_doc.doc.flagged = True  # released from quarantine as flagged afterwards
    calls = len(fake.calls)
    assert await _run(session, fake, indexed_doc, tmp_path) == _counts()
    assert _notes(tmp_path) == []
    assert all(c.summary_path is None for c in indexed_doc.chapters)
    assert len(fake.calls) == calls
    assert indexed_doc.doc.status == "ready"  # searchable as before; only the summaries go


async def test_notes_are_only_removed_inside_the_vault(session: AsyncSession, tmp_path: Path):
    d = await _make_doc(session, 1)
    outside = tmp_path / "precious.md"
    outside.write_text("keep", encoding="utf-8")
    d.chapters[0].summary_path = "../precious.md"
    d.doc.flagged = True
    await session.flush()
    await _run(session, FakeCompleter([]), d, tmp_path)
    assert outside.exists()
