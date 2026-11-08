"""Red-team tests for RAG pipeline with poisoned notes (Phase 2b Task 7 / SEC-37–SEC-42)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select

from techradar.db.models import Chunk
from techradar.rag.answer import answer_question
from techradar.rag.chunker import parse_front_matter, split_markdown
from techradar.rag.indexer import doc_meta
from techradar.rag.retrieve import RagDeps, RetrieveFilters, retrieve
from techradar.security.text import sanitize_text
from techradar.settings import Settings
from tests.fakes import FakeCompleter, FakeEmbedder, FakeReranker
from tests.security.redteam_helpers import attacker_answer

NOTES_DIR = Path("security/redteam/notes")


class MockResult:
    """Mock query result supporting both tuple iterations and scalar mappings."""

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
    """Mock database session that applies generated chunk exclusion filter."""

    def __init__(self, chunks: list[Chunk]) -> None:
        self.chunks = chunks

    async def execute(self, stmt: Any) -> MockResult:
        col_desc = getattr(stmt, "column_descriptions", None)
        target = col_desc[0]["name"] if col_desc else "unknown"
        where_clause = str(getattr(stmt, "whereclause", ""))
        has_generated_filter = "generated" in where_clause.lower() and (
            "false" in where_clause.lower() or "0" in where_clause
        )

        if target == "id":
            res_ids = []
            for c in self.chunks:
                if has_generated_filter and c.generated:
                    continue
                res_ids.append(c.id)
            return MockResult(res_ids)
        elif target == "Chunk":
            # Hydrate chunks, obeying candidate filtering if present
            return MockResult(
                [c for c in self.chunks if not (has_generated_filter and c.generated)]
            )
        elif target == "text":
            return MockResult([c.text for c in self.chunks])
        return MockResult([])


class MockSessionCtx:
    def __init__(self, session: MockSession) -> None:
        self.session = session

    async def __aenter__(self) -> MockSession:
        return self.session

    async def __aexit__(self, *args: Any) -> None:
        pass


class MockSessionFactory:
    def __init__(self, chunks: list[Chunk]) -> None:
        self.chunks = chunks

    def __call__(self) -> MockSessionCtx:
        return MockSessionCtx(MockSession(self.chunks))


async def chunk_texts_contain_tag_chars(deps: RagDeps) -> bool:
    """Check if any chunk text in the index contains Unicode tag characters (U+E0000-U+E007F)."""
    async with deps.ro_session_factory() as session:
        stmt = select(Chunk.text)
        res = await session.execute(stmt)
        texts = [row[0] if isinstance(row, tuple | list) else str(row) for row in res.all()]
        return any(0xE0000 <= ord(c) <= 0xE007F for text in texts for c in text)


@pytest.fixture
def rag_deps_with_poison() -> RagDeps:
    """Index the red-team poisoned notes into chunks and return RagDeps."""
    notes = [
        "01_ignore_and_link.md",
        "02_fake_citation_bait.md",
        "03_answer_loop.md",
        "04_hidden_unicode.md",
    ]
    chunks: list[Chunk] = []

    for i, note_name in enumerate(notes, start=1):
        p = NOTES_DIR / note_name
        if not p.exists():
            continue
        raw_text = p.read_text(encoding="utf-8")
        fm, body = parse_front_matter(raw_text)
        clean_text = sanitize_text(body)
        meta = doc_meta(fm)
        split_chunks = split_markdown(clean_text, f"security/redteam/notes/{note_name}")
        for c in split_chunks:
            chunks.append(
                Chunk(
                    id=i,
                    doc_path=f"security/redteam/notes/{note_name}",
                    doc_kind=meta.doc_kind,
                    title=meta.title,
                    heading_path=c.heading_path,
                    ordinal=c.ordinal,
                    text=c.text,
                    lang="en",
                    section=meta.section,
                    exam_tags=meta.exam_tags,
                    verified=meta.verified,
                    generated=meta.generated,
                    flagged=False,
                    source_domains=meta.source_domains,
                    content_hash=f"hash_{i}",
                    embedding=[1.0] + [0.0] * 1023,
                )
            )

    settings = Settings(
        telegram_owner_chat_id=1,
        rag_min_score=0.30,
        max_question_chars=500,
    )
    return RagDeps(
        ro_session_factory=MockSessionFactory(chunks),  # type: ignore[arg-type]
        completer=FakeCompleter([]),
        embedder=FakeEmbedder(dim=1024),
        reranker=FakeReranker(default=0.90),
        settings=settings,
    )


async def test_rag_poisoned_note_contained(rag_deps_with_poison: RagDeps) -> None:
    """Verify prompt injection attempt results in status='needs_review' and no links."""
    rag_deps_with_poison.completer = FakeCompleter(attacker_answer("ignore_and_link.md") * 2)

    a = await answer_question("What does the note say?", rag_deps_with_poison)
    assert a.status == "needs_review" and "http" not in a.text


async def test_generated_answer_never_retrieved_by_default(
    rag_deps_with_poison: RagDeps,
) -> None:
    """Verify chunks with doc_kind='answer' or generated=True are excluded by default."""
    hits = await retrieve("false claim", rag_deps_with_poison, RetrieveFilters())
    assert all(h.doc_kind != "answer" for h in hits)
    assert all(not h.generated for h in hits)


async def test_hidden_unicode_stripped_in_index(
    rag_deps_with_poison: RagDeps,
) -> None:
    """Verify unicode tag characters are stripped during indexing."""
    assert not await chunk_texts_contain_tag_chars(rag_deps_with_poison)
