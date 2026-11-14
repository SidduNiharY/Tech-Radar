"""Book scope and multi-query retrieval (Phase 2c Task 8).

The first group runs everywhere (SQL shape and fusion with a mocked session); the `db` group
needs the server database (`make test-db`).
"""

import importlib
import os
from collections.abc import AsyncGenerator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import async_sessionmaker

from techradar.db.engine import make_engine
from techradar.db.models import Chunk, LibraryDoc
from techradar.rag.expand import load_neighbors
from techradar.rag.retrieve import (
    RagDeps,
    RetrieveFilters,
    keyword_search,
    retrieve,
    retrieve_multi,
    vector_search,
)
from techradar.settings import Settings
from tests.fakes import FakeCompleter, FakeEmbedder, FakeReranker

retrieve_mod = importlib.import_module("techradar.rag.retrieve")  # the module, not the function

# --- no database needed ------------------------------------------------------------------


class RecordingSession:
    """Captures the statements sent to the database."""

    def __init__(self) -> None:
        self.stmts: list[Any] = []

    async def execute(self, stmt: Any) -> Any:
        self.stmts.append(stmt)

        class Res:
            def all(self) -> list[Any]:
                return []

        return Res()


def _sql(stmt: Any) -> str:
    """The statement as sent to the driver, plus its bound values (no literal rendering)."""
    compiled = stmt.compile(dialect=postgresql.dialect())
    sql = str(compiled)
    for name, value in compiled.params.items():
        sql = sql.replace(f"%({name})s", repr(value))
    return sql


@pytest.mark.parametrize("doc_id", [1, 10, 21])
async def test_vector_search_scopes_with_exact_integer_equality(doc_id: int) -> None:
    session = RecordingSession()
    await vector_search(session, [0.0] * 1024, RetrieveFilters(), 5, doc_id=doc_id)  # type: ignore[arg-type]
    sql = _sql(session.stmts[0])
    assert f"chunks.doc_id = {doc_id}" in sql
    assert "LIKE" not in sql.upper()


@pytest.mark.parametrize("doc_id", [1, 10, 21])
async def test_keyword_search_scopes_with_exact_integer_equality(doc_id: int) -> None:
    session = RecordingSession()
    await keyword_search(session, "repo rate", RetrieveFilters(), 5, doc_id=doc_id)  # type: ignore[arg-type]
    sql = _sql(session.stmts[0])
    assert f"chunks.doc_id = {doc_id}" in sql
    assert "LIKE" not in sql.upper()


async def test_no_doc_id_means_no_doc_filter() -> None:
    session = RecordingSession()
    await vector_search(session, [0.0] * 1024, RetrieveFilters(), 5)  # type: ignore[arg-type]
    await keyword_search(session, "repo rate", RetrieveFilters(), 5)  # type: ignore[arg-type]
    assert all("chunks.doc_id" not in _sql(s) for s in session.stmts)


@pytest.mark.parametrize("bad", ["1", "1; DROP TABLE chunks", 1.5, True])
async def test_doc_id_must_be_a_real_integer(bad: Any) -> None:
    session = RecordingSession()
    with pytest.raises(TypeError):
        await vector_search(session, [0.0] * 1024, RetrieveFilters(), 5, doc_id=bad)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        await keyword_search(session, "x", RetrieveFilters(), 5, doc_id=bad)  # type: ignore[arg-type]
    assert session.stmts == []


def _chunk(cid: int, text_: str, doc_id: int | None = 1, ordinal: int = 1) -> Chunk:
    return Chunk(
        id=cid,
        doc_path=f"library/{doc_id}/book.md",
        doc_kind="library",
        title="Book",
        heading_path=["Ch"],
        ordinal=ordinal,
        text=text_,
        lang="en",
        content_hash="h" * 64,
        generated=False,
        flagged=False,
        verified=True,
        doc_id=doc_id,
    )


class ChunkSession:
    def __init__(self, chunks: list[Chunk]) -> None:
        self.chunks = chunks

    async def execute(self, stmt: Any) -> Any:
        chunks = self.chunks

        class Res:
            def scalars(self) -> Any:
                return SimpleNamespace(all=lambda: chunks)

        return Res()


def _mock_deps(chunks: list[Chunk], table: dict[str, list[float]]) -> RagDeps:
    session = ChunkSession(chunks)

    class Ctx:
        async def __aenter__(self) -> ChunkSession:
            return session

        async def __aexit__(self, *args: object) -> None:
            return None

    return RagDeps(
        ro_session_factory=lambda: Ctx(),  # type: ignore[arg-type,return-value]
        completer=FakeCompleter([]),
        embedder=FakeEmbedder(dim=4, table=table),
        reranker=FakeReranker(default=0.5),
        settings=Settings(telegram_owner_chat_id=1),
    )


async def test_retrieve_multi_fuses_all_queries_and_embeds_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chunks = [_chunk(i, f"text {i}", ordinal=i) for i in (1, 2, 3, 4)]
    table = {"q1": [1.0, 0.0, 0.0, 0.0], "q2": [0.0, 1.0, 0.0, 0.0]}
    vec_by_query = {(1.0, 0.0, 0.0, 0.0): [1, 2], (0.0, 1.0, 0.0, 0.0): [3, 4]}
    seen: list[dict[str, Any]] = []

    async def fake_vec(session: Any, qvec: Any, f: Any, limit: int, **kw: Any) -> list[int]:
        seen.append(kw)
        return vec_by_query[tuple(qvec)]

    async def fake_kw(session: Any, query: str, f: Any, limit: int, **kw: Any) -> list[int]:
        seen.append(kw)
        return {"q1": [2], "q2": [3]}[query]

    monkeypatch.setattr(retrieve_mod, "vector_search", fake_vec)
    monkeypatch.setattr(retrieve_mod, "keyword_search", fake_kw)
    deps = _mock_deps(chunks, table)

    hits = await retrieve_multi(["q1", "q2"], deps, doc_id=1)

    assert deps.embedder.calls == [["q1", "q2"]]  # type: ignore[attr-defined]
    assert {h.chunk_id for h in hits} == {1, 2, 3, 4}
    assert all(kw == {"doc_id": 1} for kw in seen)
    assert len(seen) == 4  # a vector and a keyword search per query


async def test_retrieve_multi_scores_with_the_first_query(monkeypatch: pytest.MonkeyPatch) -> None:
    chunks = [_chunk(1, "text 1")]

    async def fake_ids(*args: Any, **kw: Any) -> list[int]:
        return [1]

    monkeypatch.setattr(retrieve_mod, "vector_search", fake_ids)
    monkeypatch.setattr(retrieve_mod, "keyword_search", fake_ids)
    deps = _mock_deps(chunks, {})
    await retrieve_multi(["original?", "rewrite one"], deps)
    assert deps.reranker.calls[0][0] == "original?"  # type: ignore[attr-defined]


async def test_retrieve_multi_dedupes_queries_and_survives_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def none(*args: Any, **kw: Any) -> list[int]:
        return []

    monkeypatch.setattr(retrieve_mod, "vector_search", none)
    monkeypatch.setattr(retrieve_mod, "keyword_search", none)
    deps = _mock_deps([], {})
    assert await retrieve_multi(["a", "a"], deps) == []
    assert deps.embedder.calls == [["a"]]  # type: ignore[attr-defined]
    assert await retrieve_multi([], deps) == []


async def test_candidates_from_another_book_are_dropped_in_memory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Defence in depth: even if a search ever returned another book's chunk ids, the loaded
    # chunks are checked against the scope before they can reach the model.
    chunks = [_chunk(1, "mine", doc_id=1), _chunk(2, "other", doc_id=2), _chunk(3, "none", None)]

    async def leaky(*args: Any, **kw: Any) -> list[int]:
        return [1, 2, 3]

    monkeypatch.setattr(retrieve_mod, "vector_search", leaky)
    monkeypatch.setattr(retrieve_mod, "keyword_search", leaky)
    deps = _mock_deps(chunks, {})
    assert [h.chunk_id for h in await retrieve("q", deps, doc_id=1)] == [1]
    assert {h.chunk_id for h in await retrieve("q", deps)} == {1, 2, 3}


async def test_retrieve_passes_doc_id_through(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[Any] = []

    async def none(*args: Any, **kw: Any) -> list[int]:
        seen.append(kw.get("doc_id"))
        return []

    monkeypatch.setattr(retrieve_mod, "vector_search", none)
    monkeypatch.setattr(retrieve_mod, "keyword_search", none)
    deps = _mock_deps([], {})
    await retrieve("q", deps, doc_id=10)
    assert seen == [10, 10]


# --- database tests (server only: `make test-db`) -----------------------------------------


def _settings() -> Settings:
    return Settings(
        telegram_owner_chat_id=1,
        db_host="127.0.0.1",
        db_port=55432,
        db_name="techradar",
        secrets_dir=Path("secrets"),
    )


VEC = [1.0] + [0.0] * 1023


@pytest.fixture
async def two_books() -> AsyncGenerator[SimpleNamespace]:
    """Library docs with ids 1, 10 and 21 (ids that are substrings of each other)."""
    if os.environ.get("TR_DB_TESTS_MAY_WIPE") != "1":
        pytest.skip("set TR_DB_TESTS_MAY_WIPE=1 (make test-db does) to allow wiping test tables")
    settings = _settings()

    async def wipe() -> None:
        engine = make_engine("migrator", settings)
        async with engine.begin() as conn:
            await conn.execute(
                text("TRUNCATE techradar.chunks, techradar.library_docs RESTART IDENTITY CASCADE")
            )
        await engine.dispose()

    await wipe()
    app_engine = make_engine("app", settings)
    ro_engine = make_engine("ro", settings)
    app_factory = async_sessionmaker(app_engine, expire_on_commit=False)
    ro_factory = async_sessionmaker(ro_engine, expire_on_commit=False)

    async with app_factory() as session:
        docs = [
            LibraryDoc(
                sha256=f"{i:064x}",
                title=f"Book {i}",
                kind="pdf",
                origin="library",
                original_path=f"originals/{i}.pdf",
                size_bytes=10,
                status="ready",
                trust="official",
            )
            for i in range(1, 22)
        ]
        session.add_all(docs)
        await session.flush()
        ids = {d.id for d in docs}
        assert {1, 10, 21} <= ids  # RESTART IDENTITY gives 1..21
        first, tenth, twenty_first = docs[0].id, docs[9].id, docs[20].id
        session.add_all(
            [
                Chunk(
                    doc_path=f"library/{doc_id}/chapter-1.md",
                    doc_kind="library",
                    title=f"Book {doc_id}",
                    heading_path=["Money"],
                    ordinal=ordinal,
                    text=f"The repo rate is set by the RBI, part {ordinal} of book {doc_id}.",
                    lang="en",
                    content_hash=f"{doc_id:02d}{ordinal:02d}".ljust(64, "0"),
                    embedding=VEC,
                    doc_id=doc_id,
                    chapter_id=doc_id * 100,
                    generated=False,
                    verified=True,
                )
                for doc_id in (first, tenth, twenty_first)
                for ordinal in (1, 2, 3)
            ]
            # A vault note whose path mentions library/1/ but has no doc_id.
            + [
                Chunk(
                    doc_path="notes/library/1/stray.md",
                    doc_kind="news",
                    title="Stray",
                    heading_path=[],
                    ordinal=1,
                    text="The repo rate stray note.",
                    lang="en",
                    content_hash="ff" * 32,
                    embedding=VEC,
                    doc_id=None,
                    generated=False,
                    verified=True,
                )
            ]
        )
        await session.commit()

    deps = RagDeps(
        ro_session_factory=ro_factory,
        completer=FakeCompleter([]),
        embedder=FakeEmbedder(dim=1024, table={"repo rate": VEC}),
        reranker=FakeReranker(default=0.7),
        settings=settings,
    )
    try:
        yield SimpleNamespace(
            first=first, tenth=tenth, twenty_first=twenty_first, deps=deps, ro_factory=ro_factory
        )
    finally:
        await app_engine.dispose()
        await ro_engine.dispose()
        await wipe()


@pytest.fixture
def rag_deps(two_books: SimpleNamespace) -> RagDeps:
    return two_books.deps


@pytest.mark.db
async def test_doc_scope_returns_only_that_book(rag_deps, two_books):
    hits = await retrieve("repo rate", rag_deps, doc_id=two_books.first)
    assert hits
    assert {h.doc_id for h in hits} == {two_books.first}


@pytest.mark.db
async def test_scoping_to_1_never_returns_10_or_21(rag_deps, two_books):
    assert (two_books.first, two_books.tenth, two_books.twenty_first) == (1, 10, 21)
    hits = await retrieve("repo rate", rag_deps, doc_id=1)
    assert hits
    assert {h.doc_id for h in hits} == {1}
    assert all(h.doc_path.startswith("library/1/") for h in hits)
    # and the stray vault note whose path looks like the book's is not a book chunk
    assert not any(h.doc_path.startswith("notes/") for h in hits)
    hits10 = await retrieve("repo rate", rag_deps, doc_id=10)
    assert {h.doc_id for h in hits10} == {10}


@pytest.mark.db
async def test_multi_query_scope_holds_for_every_query(rag_deps, two_books):
    rag_deps.embedder.table["repo rate RBI"] = VEC  # type: ignore[attr-defined]
    hits = await retrieve_multi(["repo rate", "repo rate RBI"], rag_deps, doc_id=1)
    assert hits
    assert {h.doc_id for h in hits} == {1}


@pytest.mark.db
async def test_no_scope_still_searches_everything(rag_deps, two_books):
    hits = await retrieve("repo rate", rag_deps)
    assert len({h.doc_id for h in hits}) > 1  # 6 of 10 chunks, in groups of 3


@pytest.mark.db
async def test_load_neighbors_finds_ordinal_plus_minus_one_in_the_same_book(rag_deps, two_books):
    hits = await retrieve("repo rate", rag_deps, doc_id=two_books.first)
    middle = next(h for h in hits if h.ordinal == 2)
    neighbors = await load_neighbors(rag_deps, [middle])
    before, after = neighbors(middle)
    assert before is not None and after is not None
    assert (before.ordinal, after.ordinal) == (1, 3)
    assert {before.doc_id, after.doc_id} == {two_books.first}


@pytest.mark.db
async def test_load_neighbors_at_the_edges_and_never_other_books(rag_deps, two_books):
    hits = await retrieve("repo rate", rag_deps, doc_id=two_books.first)
    last = next(h for h in hits if h.ordinal == 3)
    first_chunk = next(h for h in hits if h.ordinal == 1)
    neighbors = await load_neighbors(rag_deps, [last, first_chunk])
    assert neighbors(last)[1] is None
    assert neighbors(first_chunk)[0] is None
    for h in (last, first_chunk):
        for n in neighbors(h):
            assert n is None or n.doc_id == two_books.first
