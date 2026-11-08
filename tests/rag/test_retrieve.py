"""Tests for hybrid retrieval and the cross-encoder reranker (Phase 2b Task 4).

SEC: SEC-23, SEC-39, SEC-40, SEC-41, SEC-42.
"""

from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from techradar.db.engine import make_engine
from techradar.db.models import Chunk
from techradar.rag.rerank import CrossEncoderReranker, sigmoid
from techradar.rag.retrieve import (
    RagDeps,
    RetrieveFilters,
    keyword_search,
    retrieve,
    rrf,
)
from techradar.settings import Settings
from tests.fakes import FakeCompleter, FakeEmbedder, FakeReranker


def test_rrf_prefers_items_in_both_lists() -> None:
    # 3 is in both lists; 1, 2, 4 are only in one.
    ranked = rrf([[1, 2, 3], [3, 4]])
    assert ranked[0][0] == 3


def test_rrf_handles_empty_lists() -> None:
    assert rrf([]) == []
    assert rrf([[]]) == []


def test_sigmoid_bounds() -> None:
    assert sigmoid(0.0) == pytest.approx(0.5)
    assert 0.0 <= sigmoid(-1000.0) <= 0.001
    assert 0.999 <= sigmoid(1000.0) <= 1.0


def test_cross_encoder_reranker_with_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    class MockCrossEncoder:
        def __init__(self, path: str, device: str = "cpu") -> None:
            self.path = path
            self.device = device

        def predict(self, pairs: list[list[str]]) -> list[float]:
            return [2.0, -2.0]

    import sys
    import types

    fake_mod = types.ModuleType("sentence_transformers")
    fake_mod.CrossEncoder = MockCrossEncoder  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_mod)

    reranker = CrossEncoderReranker(Path("/fake/path"), device="cpu")
    scores = reranker.score("query", ["passage 1", "passage 2"])
    assert len(scores) == 2
    assert scores[0] > scores[1]
    assert all(0.0 <= s <= 1.0 for s in scores)


async def test_retrieve_empty_when_no_candidates() -> None:
    class MockSession:
        async def execute(self, stmt: object) -> object:
            class MockRes:
                def all(self) -> list[object]:
                    return []

            return MockRes()

    class MockSessionFactory:
        def __call__(self) -> object:
            session = MockSession()

            class Ctx:
                async def __aenter__(self) -> MockSession:
                    return session

                async def __aexit__(self, *args: object) -> None:
                    pass

            return Ctx()

    deps = RagDeps(
        ro_session_factory=MockSessionFactory(),  # type: ignore[arg-type]
        completer=FakeCompleter([]),
        embedder=FakeEmbedder(dim=1024),
        reranker=FakeReranker(),
        settings=Settings(telegram_owner_chat_id=1),
    )
    hits = await retrieve("question?", deps)
    assert hits == []


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
async def rag_deps_seeded(db_settings: Settings) -> AsyncGenerator[RagDeps]:
    app_engine = make_engine("app", db_settings)
    ro_engine = make_engine("ro", db_settings)
    app_session_factory = async_sessionmaker(app_engine, expire_on_commit=False)
    ro_session_factory = async_sessionmaker(ro_engine, expire_on_commit=False)

    sample_vec_repo = [1.0] + [0.0] * 1023
    sample_vec_art = [0.0, 1.0] + [0.0] * 1022
    sample_vec_dev = [0.0, 0.0, 1.0] + [0.0] * 1021

    embedder_table = {
        "repo rate": sample_vec_repo,
        "Article 370": sample_vec_art,
        "मुद्रास्फीति": sample_vec_dev,
        "inflation": sample_vec_dev,
    }
    embedder = FakeEmbedder(dim=1024, table=embedder_table)
    completer = FakeCompleter([])
    reranker = FakeReranker(
        scores={
            "RBI repo rate policy decision.": 0.95,
            "RBI kept the repo rate unchanged at 6.5%.": 0.90,
        },
        default=0.60,
    )

    test_paths = [
        "notes/repo1.md",
        "notes/repo2.md",
        "notes/repo_gen.md",
        "notes/repo_unv.md",
        "notes/art370.md",
        "notes/hindi.md",
        "notes/dummy1.md",
        "notes/dummy2.md",
        "notes/dummy3.md",
        "notes/dummy4.md",
    ]

    async with app_session_factory() as session:
        # Clean up any leftover test chunks
        await session.execute(
            text("DELETE FROM techradar.chunks WHERE doc_path = ANY(:paths)"),
            {"paths": test_paths},
        )
        await session.commit()

        chunks = [
            Chunk(
                doc_path="notes/repo1.md",
                doc_kind="news",
                title="RBI Repo Decision",
                heading_path=["Economy", "Rates"],
                ordinal=1,
                text="RBI repo rate policy decision.",
                lang="en",
                section="economy",
                exam_tags=["banking"],
                verified=True,
                generated=False,
                content_hash="h1" * 32,
                embedding=sample_vec_repo,
            ),
            Chunk(
                doc_path="notes/repo2.md",
                doc_kind="news",
                title="Monetary Policy",
                heading_path=["Economy"],
                ordinal=1,
                text="RBI kept the repo rate unchanged at 6.5%.",
                lang="en",
                section="economy",
                exam_tags=["banking"],
                verified=True,
                generated=False,
                content_hash="h2" * 32,
                embedding=sample_vec_repo,
            ),
            Chunk(
                doc_path="notes/repo_gen.md",
                doc_kind="answer",
                title="Generated Q&A",
                heading_path=["Q&A"],
                ordinal=1,
                text="Generated answer discussing repo rate.",
                lang="en",
                section="economy",
                exam_tags=["banking"],
                verified=True,
                generated=True,
                content_hash="h3" * 32,
                embedding=sample_vec_repo,
            ),
            Chunk(
                doc_path="notes/repo_unv.md",
                doc_kind="user",
                title="Unverified Notes",
                heading_path=["Drafts"],
                ordinal=1,
                text="Unverified draft thoughts on repo rate.",
                lang="en",
                section="economy",
                exam_tags=[],
                verified=False,
                generated=False,
                content_hash="h4" * 32,
                embedding=sample_vec_repo,
            ),
            Chunk(
                doc_path="notes/art370.md",
                doc_kind="news",
                title="Constitutional Bench",
                heading_path=["Polity"],
                ordinal=1,
                text="Supreme court hearing on Article 370 provisions.",
                lang="en",
                section="polity",
                exam_tags=["gate"],
                verified=True,
                generated=False,
                content_hash="h5" * 32,
                embedding=sample_vec_art,
            ),
            Chunk(
                doc_path="notes/hindi.md",
                doc_kind="news",
                title="मुद्रास्फीति रिपोर्ट",
                heading_path=["अर्थव्यवस्था"],
                ordinal=1,
                text="चालू वित्त वर्ष में मुद्रास्फीति दर में वृद्धि दर्ज की गई।",
                lang="hi",
                section="economy",
                exam_tags=[],
                verified=True,
                generated=False,
                content_hash="h6" * 32,
                embedding=sample_vec_dev,
            ),
        ]
        # Add 4 dummy chunks to test max 6 limit
        for i in range(1, 5):
            chunks.append(
                Chunk(
                    doc_path=f"notes/dummy{i}.md",
                    doc_kind="news",
                    title=f"Dummy note {i}",
                    heading_path=[],
                    ordinal=1,
                    text=f"Inflation discussion paragraph {i}.",
                    lang="en",
                    section="economy",
                    exam_tags=[],
                    verified=True,
                    generated=False,
                    content_hash=f"d{i}" * 32,
                    embedding=sample_vec_dev,
                )
            )

        session.add_all(chunks)
        await session.commit()

    deps = RagDeps(
        ro_session_factory=ro_session_factory,
        completer=completer,
        embedder=embedder,
        reranker=reranker,
        settings=db_settings,
    )

    try:
        yield deps
    finally:
        async with app_session_factory() as session:
            await session.execute(
                text("DELETE FROM techradar.chunks WHERE doc_path = ANY(:paths)"),
                {"paths": test_paths},
            )
            await session.commit()
        await app_engine.dispose()
        await ro_engine.dispose()


@pytest.mark.db
async def test_generated_excluded_by_default(rag_deps_seeded: RagDeps) -> None:
    hits = await retrieve("repo rate", rag_deps_seeded, RetrieveFilters())
    assert len(hits) > 0
    assert all(not h.generated for h in hits)


@pytest.mark.db
async def test_verified_only_filter(rag_deps_seeded: RagDeps) -> None:
    hits = await retrieve("repo rate", rag_deps_seeded, RetrieveFilters(verified_only=True))
    assert len(hits) > 0
    assert all(h.verified for h in hits)


@pytest.mark.db
async def test_keyword_search_finds_exact_term(rag_deps_seeded: RagDeps) -> None:
    hits = await retrieve("Article 370", rag_deps_seeded, RetrieveFilters())
    assert any("Article 370" in h.text for h in hits)


@pytest.mark.db
async def test_keyword_search_handles_devanagari(rag_deps_seeded: RagDeps) -> None:
    async with rag_deps_seeded.ro_session_factory() as session:
        ids = await keyword_search(session, "मुद्रास्फीति", RetrieveFilters(), 30)
        assert len(ids) > 0


@pytest.mark.db
async def test_retrieve_returns_at_most_six_sorted(rag_deps_seeded: RagDeps) -> None:
    hits = await retrieve("inflation", rag_deps_seeded, RetrieveFilters())
    assert 0 < len(hits) <= 6
    scores = [h.score for h in hits]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.db
async def test_retrieve_uses_read_only_role(rag_deps_seeded: RagDeps) -> None:
    assert rag_deps_seeded.ro_session_factory.kw["bind"].url.username == "tr_ro"
