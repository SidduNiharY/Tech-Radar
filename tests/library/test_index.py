"""Library chapter indexing (Phase 2c Task 6): labels, tables, page numbers, idempotency."""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from techradar.db.engine import make_engine
from techradar.db.models import Chunk, LibraryChapter, LibraryDoc
from techradar.library.index import index_library_chapter, trust_label
from techradar.rag.indexer import IndexDeps
from techradar.settings import Settings
from tests.fakes import FakeEmbedder

CHAPTER_MD = (
    "# Money\n<!-- page 12 -->\nThe repo rate is the rate at which the RBI lends.\n\n"
    "## Banks\n<!-- page 13 -->\nCommercial banks take deposits.\n\n"
    "| a | b |\n|---|---|\n| 1 | 2 |\n\n"
    "<!-- page 14 -->\nMore about banks without a marker on top."
)


def test_trust_label_names():
    assert trust_label("official") == "official"
    assert trust_label("open") == "open"
    assert trust_label("my_own") == "my own"
    with pytest.raises(ValueError):
        trust_label("trusted")


# --- database tests (server only: `make test-db`) ------------------------------------


def _settings() -> Settings:
    return Settings(
        telegram_owner_chat_id=1,
        db_host="127.0.0.1",
        db_port=55432,
        db_name="techradar",
        secrets_dir=Path("secrets"),
    )


@pytest.fixture
async def library_db() -> AsyncGenerator[None]:
    """Empty chunks and library rows around a test; only with TR_DB_TESTS_MAY_WIPE=1."""
    if os.environ.get("TR_DB_TESTS_MAY_WIPE") != "1":
        pytest.skip("set TR_DB_TESTS_MAY_WIPE=1 (make test-db does) to allow wiping test tables")

    async def wipe() -> None:
        engine = make_engine("migrator", _settings())
        async with engine.begin() as conn:
            await conn.execute(
                text("TRUNCATE techradar.chunks, techradar.library_docs RESTART IDENTITY CASCADE")
            )
        await engine.dispose()

    await wipe()
    yield
    await wipe()


@pytest.fixture
async def index_deps(tmp_path: Path, library_db: None) -> AsyncGenerator[IndexDeps]:
    dirs = {n: tmp_path / n for n in ("vault", "library", "inbox", "raw", "jobs", "clean")}
    for d in dirs.values():
        d.mkdir()
    engine = make_engine("app", _settings())
    yield IndexDeps(
        session_factory=async_sessionmaker(engine, expire_on_commit=False),
        embedder=FakeEmbedder(dim=1024),
        vault_root=dirs["vault"],
        library_dir=dirs["library"],
        library_inbox=dirs["inbox"],
        raw_dir=dirs["raw"],
        jobs_dir=dirs["jobs"],
        clean_dir=dirs["clean"],
    )
    await engine.dispose()


@pytest.fixture
async def chapter(index_deps: IndexDeps) -> SimpleNamespace:
    """Ordinal 3 of a book titled "Indian Economy", with its text file written."""
    rel = "text/1/03.md"
    path = index_deps.library_dir / rel
    path.parent.mkdir(parents=True)
    path.write_text(CHAPTER_MD, encoding="utf-8")
    async with index_deps.session_factory() as session:
        doc = LibraryDoc(
            sha256=os.urandom(32).hex(),
            title="Indian Economy",
            kind="pdf",
            origin="library",
            original_path="originals/x.pdf",
            size_bytes=10,
            status="processing",
            trust="official",
            exam_tags=["upsc"],
        )
        session.add(doc)
        await session.flush()
        ch = LibraryChapter(doc_id=doc.id, ordinal=3, title="Money", page_start=12, text_path=rel)
        session.add(ch)
        await session.commit()
        return SimpleNamespace(id=ch.id, doc_id=doc.id, path=path)


async def _chunks(deps: IndexDeps, chapter_id: int) -> list[Chunk]:
    async with deps.session_factory() as session:
        rows = await session.execute(
            select(Chunk).where(Chunk.chapter_id == chapter_id).order_by(Chunk.ordinal)
        )
        return list(rows.scalars())


@pytest.mark.db
async def test_context_label_used_for_embedding_not_text(index_deps, chapter):
    n = await index_library_chapter(index_deps, chapter.id)
    chunks = await _chunks(index_deps, chapter.id)
    assert n == len(chunks) >= 2
    embedder = index_deps.embedder
    inputs = [t for batch in embedder.calls for t in batch]
    assert inputs[0].startswith("Indian Economy › Money › ")
    assert inputs[0] == f"{chunks[0].context_label}\n\n{chunks[0].text}"
    assert not chunks[0].text.startswith("Indian Economy ›")
    assert chunks[0].context_label == "Indian Economy › Money › Money"
    assert "Indian Economy › Money › Banks" in {c.context_label for c in chunks}


@pytest.mark.db
async def test_chunk_columns_for_library(index_deps, chapter):
    await index_library_chapter(index_deps, chapter.id)
    chunks = await _chunks(index_deps, chapter.id)
    assert [c.ordinal for c in chunks] == list(range(len(chunks)))
    for c in chunks:
        assert c.doc_path == f"library/{chapter.doc_id}/03.md"
        assert c.doc_kind == "library" and c.doc_id == chapter.doc_id
        assert c.verified is None and c.flagged is False and c.ts_start is None
        assert c.title == "Indian Economy" and c.exam_tags == ["upsc"]
        assert "<!--" not in c.text and "text/1/03.md" not in c.text
    assert chunks[0].page == 12
    assert chunks[-1].page == 14  # the last marker in or before the chunk


@pytest.mark.db
async def test_table_kept_whole_in_one_chunk(index_deps, chapter):
    await index_library_chapter(index_deps, chapter.id)
    chunks = await _chunks(index_deps, chapter.id)
    assert sum("| a | b |" in c.text for c in chunks) == 1


@pytest.mark.db
async def test_reindex_replaces_chunks(index_deps, chapter):
    first = await index_library_chapter(index_deps, chapter.id)
    chapter.path.write_text("# Money\n<!-- page 20 -->\nOnly one short paragraph now.")
    second = await index_library_chapter(index_deps, chapter.id)
    chunks = await _chunks(index_deps, chapter.id)
    assert first > second == len(chunks) == 1
    assert chunks[0].page == 20 and "short paragraph" in chunks[0].text
    async with index_deps.session_factory() as session:
        total = await session.scalar(select(func.count()).select_from(Chunk))
    assert total == 1  # nothing left over from the first run


@pytest.mark.db
async def test_reindex_same_text_keeps_same_count(index_deps, chapter):
    assert await index_library_chapter(index_deps, chapter.id) == await index_library_chapter(
        index_deps, chapter.id
    )
    async with index_deps.session_factory() as session:
        assert await session.scalar(text("select count(*) from techradar.chunks")) == len(
            await _chunks(index_deps, chapter.id)
        )


@pytest.mark.db
async def test_missing_text_file_indexes_nothing(index_deps, chapter, caplog):
    chapter.path.unlink()
    with caplog.at_level("WARNING"):
        assert await index_library_chapter(index_deps, chapter.id) == 0
    assert await _chunks(index_deps, chapter.id) == []
    assert index_deps.embedder.calls == []
    assert "nothing indexed" in caplog.text


@pytest.mark.db
async def test_empty_text_file_indexes_nothing(index_deps, chapter):
    chapter.path.write_text("  \n\n")
    assert await index_library_chapter(index_deps, chapter.id) == 0
    assert await _chunks(index_deps, chapter.id) == []


@pytest.mark.db
async def test_unknown_chapter_indexes_nothing(index_deps):
    assert await index_library_chapter(index_deps, 987654) == 0


@pytest.mark.db
async def test_text_path_outside_library_dir_is_refused(index_deps, chapter, tmp_path):
    (tmp_path / "secret.md").write_text("# S\nnot a library file")
    async with index_deps.session_factory() as session:
        row = await session.get(LibraryChapter, chapter.id)
        row.text_path = "../secret.md"
        await session.commit()
    assert await index_library_chapter(index_deps, chapter.id) == 0
    assert await _chunks(index_deps, chapter.id) == []
