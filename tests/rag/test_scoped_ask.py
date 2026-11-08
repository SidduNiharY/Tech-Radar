"""Tests for scoped document retrieval ("Ask this PDF" / Phase 4 & Phase 2c)."""

from typing import Any

import pytest

from techradar.db.models import Chunk
from techradar.rag.retrieve import RagDeps, RetrieveFilters
from techradar.rag.scoped_ask import scoped_retrieve
from techradar.settings import Settings
from tests.fakes import FakeCompleter, FakeEmbedder, FakeReranker


class MockResult:
    """Mock database query result supporting both tuple iteration and scalar lists."""

    def __init__(self, data: list[Any]) -> None:
        self._data = data

    def all(self) -> list[Any]:
        return [(d,) if not isinstance(d, tuple) else d for d in self._data]

    def scalars(self) -> Any:
        class ScalarResult:
            def __init__(self, d: list[Any]) -> None:
                self._d = d

            def all(self) -> list[Any]:
                return self._d

        return ScalarResult(self._data)


class MockSession:
    """Mock session that applies document scope and generated filtering."""

    def __init__(self, chunks: list[Chunk]) -> None:
        self.chunks = chunks

    async def execute(self, stmt: Any) -> MockResult:
        col_desc = getattr(stmt, "column_descriptions", None)
        target = col_desc[0]["name"] if col_desc else "unknown"
        params = stmt.compile().params
        where_clause = str(getattr(stmt, "whereclause", ""))

        has_generated_filter = "generated" in where_clause.lower() and (
            "false" in where_clause.lower() or "0" in where_clause
        )

        if target == "id":
            res_ids: list[int] = []
            for c in self.chunks:
                if has_generated_filter and c.generated:
                    continue
                doc_id_val = getattr(c, "doc_id", None) or c.doc_path
                # Match against bound parameters (doc_id)
                matches_param = doc_id_val in params.values() or any(
                    doc_id_val in str(v) for v in params.values()
                )
                if matches_param:
                    res_ids.append(c.id)
            return MockResult(res_ids)

        elif target == "Chunk":
            # Return chunks matching candidate IDs if present in whereclause
            return MockResult(self.chunks)

        return MockResult([])


class MockSessionCtx:
    def __init__(self, session: MockSession) -> None:
        self.session = session

    async def __aenter__(self) -> MockSession:
        return self.session

    async def __aexit__(self, *args: Any) -> None:
        pass


def make_test_deps(chunks: list[Chunk], scores: dict[str, float] | None = None) -> RagDeps:
    session = MockSession(chunks)
    return RagDeps(
        ro_session_factory=lambda: MockSessionCtx(session),  # type: ignore[arg-type]
        completer=FakeCompleter([]),
        embedder=FakeEmbedder(dim=4),
        reranker=FakeReranker(scores=scores or {}, default=0.5),
        settings=Settings(telegram_owner_chat_id=1),
    )


@pytest.mark.asyncio
async def test_scoped_retrieve_filters_by_doc_id() -> None:
    """Verifies results only contain hits from the specified doc_id."""
    c1 = Chunk(
        id=1,
        doc_path="physics_guide.pdf",
        doc_kind="pdf",
        title="Physics Guide",
        heading_path=["Quantum", "Wave"],
        ordinal=1,
        text="Wave-particle duality in quantum mechanics.",
        lang="en",
        content_hash="h1" * 32,
        embedding=[1.0, 0.0, 0.0, 0.0],
        generated=False,
    )
    c1.doc_id = "doc-physics"

    c2 = Chunk(
        id=2,
        doc_path="physics_guide.pdf",
        doc_kind="pdf",
        title="Physics Guide",
        heading_path=["Quantum", "Entanglement"],
        ordinal=2,
        text="Quantum entanglement principles.",
        lang="en",
        content_hash="h2" * 32,
        embedding=[1.0, 0.0, 0.0, 0.0],
        generated=False,
    )
    c2.doc_id = "doc-physics"

    c3 = Chunk(
        id=3,
        doc_path="history_guide.pdf",
        doc_kind="pdf",
        title="History Guide",
        heading_path=["Modern"],
        ordinal=1,
        text="Quantum developments in 20th century warfare history.",
        lang="en",
        content_hash="h3" * 32,
        embedding=[1.0, 0.0, 0.0, 0.0],
        generated=False,
    )
    c3.doc_id = "doc-history"

    scores = {
        "Wave-particle duality in quantum mechanics.": 0.95,
        "Quantum entanglement principles.": 0.90,
        "Quantum developments in 20th century warfare history.": 0.99,  # High score but wrong doc
    }
    deps = make_test_deps([c1, c2, c3], scores=scores)

    # Scoped retrieve strictly for doc-physics
    hits = await scoped_retrieve("quantum mechanics", "doc-physics", deps)

    assert len(hits) == 2
    # Verify every returned hit belongs strictly to doc-physics
    assert all(getattr(h, "doc_id", None) == "doc-physics" for h in hits)
    # Ensure chunk 3 from doc-history was NEVER returned despite high reranker score
    assert not any(h.chunk_id == 3 for h in hits)
    # Ensure ordered by score descending
    assert hits[0].score >= hits[1].score


@pytest.mark.asyncio
async def test_scoped_retrieve_returns_top_k() -> None:
    """Verifies that the k limit is respected and results are ranked."""
    chunks: list[Chunk] = []
    scores: dict[str, float] = {}

    for i in range(1, 11):
        text_content = f"Chapter section text paragraph {i} discussing algorithms."
        c = Chunk(
            id=i,
            doc_path="algorithms_handbook.pdf",
            doc_kind="pdf",
            title="Algorithms Handbook",
            heading_path=["Sorting"],
            ordinal=i,
            text=text_content,
            lang="en",
            content_hash=f"hash{i:02d}" * 8,
            embedding=[0.5, 0.5, 0.0, 0.0],
            generated=False,
        )
        c.doc_id = "doc-algo"
        chunks.append(c)
        scores[text_content] = 0.50 + (i * 0.04)  # 0.54, 0.58, ... 0.90

    deps = make_test_deps(chunks, scores=scores)

    # Test with k=3
    hits_k3 = await scoped_retrieve("algorithms", "doc-algo", deps, k=3)
    assert len(hits_k3) == 3
    # Check score descending order
    assert hits_k3[0].score >= hits_k3[1].score >= hits_k3[2].score
    assert hits_k3[0].chunk_id == 10  # highest score 0.90
    assert hits_k3[1].chunk_id == 9  # score 0.86
    assert hits_k3[2].chunk_id == 8  # score 0.82

    # Test with k=6
    hits_k6 = await scoped_retrieve("algorithms", "doc-algo", deps, k=6)
    assert len(hits_k6) == 6
    assert hits_k6[0].chunk_id == 10


@pytest.mark.asyncio
async def test_scoped_retrieve_empty_when_no_match() -> None:
    """Querying an unknown doc_id returns an empty hit list."""
    c = Chunk(
        id=1,
        doc_path="notes.pdf",
        doc_kind="pdf",
        title="Notes",
        heading_path=[],
        ordinal=1,
        text="Sample text",
        lang="en",
        content_hash="h" * 64,
        embedding=[1.0, 0.0, 0.0, 0.0],
        generated=False,
    )
    c.doc_id = "existing-doc"
    deps = make_test_deps([c])

    hits = await scoped_retrieve("query", "non-existent-doc", deps)
    assert hits == []


@pytest.mark.asyncio
async def test_scoped_retrieve_excludes_generated_by_default() -> None:
    """Generated summary chunks are excluded by default."""
    c1 = Chunk(
        id=1,
        doc_path="doc.pdf",
        doc_kind="pdf",
        title="Doc",
        heading_path=[],
        ordinal=1,
        text="Human authored content",
        lang="en",
        content_hash="h1" * 32,
        embedding=[1.0, 0.0, 0.0, 0.0],
        generated=False,
    )
    c1.doc_id = "target-doc"

    c2 = Chunk(
        id=2,
        doc_path="doc.pdf",
        doc_kind="pdf",
        title="Doc",
        heading_path=[],
        ordinal=2,
        text="Generated summary of chapter",
        lang="en",
        content_hash="h2" * 32,
        embedding=[1.0, 0.0, 0.0, 0.0],
        generated=True,
    )
    c2.doc_id = "target-doc"

    deps = make_test_deps(
        [c1, c2],
        scores={
            "Human authored content": 0.8,
            "Generated summary of chapter": 0.95,
        },
    )

    # By default, generated is excluded
    hits = await scoped_retrieve("summary", "target-doc", deps)
    assert len(hits) == 1
    assert hits[0].chunk_id == 1

    # When explicitly included, both return
    hits_all = await scoped_retrieve(
        "summary",
        "target-doc",
        deps,
        f=RetrieveFilters(include_generated=True),
    )
    assert len(hits_all) == 2
