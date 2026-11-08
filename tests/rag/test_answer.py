"""Tests for grounded answers with checked citations (Phase 2b Task 5).

SEC: SEC-37, SEC-38, SEC-41, SEC-42.
"""

from typing import Any

import pytest

from techradar.rag.answer import (
    NOT_FOUND,
    answer_question,
    build_context,
    check_citations,
)
from techradar.rag.retrieve import Hit, RagDeps
from techradar.settings import Settings
from tests.fakes import FakeCompleter, FakeEmbedder, FakeReranker

HITS = [
    Hit(
        chunk_id=1,
        doc_path="notes/policy.md",
        title="RBI Policy",
        heading_path=["Economy", "Rates"],
        text="RBI maintained the repo rate at 6.5%.",
        doc_kind="news",
        verified=True,
        generated=False,
        score=0.92,
    ),
    Hit(
        chunk_id=2,
        doc_path="notes/inflation.md",
        title="Inflation Print",
        heading_path=["Economy"],
        text="CPI inflation eased to 4.8%.",
        doc_kind="news",
        verified=True,
        generated=False,
        score=0.85,
    ),
]


class MockSessionFactory:
    def __init__(self, hits: list[Hit] | None = None) -> None:
        self.hits = hits or []

    def __call__(self) -> Any:
        class Ctx:
            async def __aenter__(self) -> Any:
                return self

            async def __aexit__(self, *args: Any) -> None:
                pass

        return Ctx()


def make_deps(
    hits: list[Hit],
    completer: FakeCompleter | None = None,
    min_score: float = 0.30,
) -> RagDeps:
    settings = Settings(
        telegram_owner_chat_id=1,
        rag_min_score=min_score,
        max_question_chars=500,
    )
    scores = {h.text: h.score for h in hits}
    reranker = FakeReranker(scores=scores, default=0.5)
    embedder = FakeEmbedder(dim=1024)
    if completer is None:
        completer = FakeCompleter([])

    return RagDeps(
        ro_session_factory=MockSessionFactory(hits),  # type: ignore[arg-type]
        completer=completer,
        embedder=embedder,
        reranker=reranker,
        settings=settings,
    )


def test_build_context_wraps_untrusted_and_numbers() -> None:
    ctx = build_context(HITS)
    assert "<<UNTRUSTED" in ctx
    assert "[C1] RBI Policy › Economy › Rates" in ctx
    assert "[C2] Inflation Print › Economy" in ctx
    assert "<<END" in ctx


def test_check_citations_valid() -> None:
    assert check_citations("Claim [C1] and other claim [C2].", ["C1", "C2"], 2)


def test_check_citations_invalid_out_of_bounds() -> None:
    assert not check_citations("Claim [C3].", ["C3"], 2)
    assert not check_citations("Claim [C1].", ["C1", "C9"], 2)
    assert not check_citations("Claim without citation.", [], 2)


@pytest.fixture
def deps_no_hits(monkeypatch: pytest.MonkeyPatch) -> RagDeps:
    deps = make_deps([])

    async def mock_retrieve(*args: Any, **kwargs: Any) -> list[Hit]:
        return []

    monkeypatch.setattr("techradar.rag.answer.retrieve", mock_retrieve)
    return deps


@pytest.fixture
def deps_low_scores(monkeypatch: pytest.MonkeyPatch) -> RagDeps:
    low_hit = Hit(
        chunk_id=1,
        doc_path="p.md",
        title="T",
        heading_path=[],
        text="text",
        doc_kind="news",
        verified=True,
        generated=False,
        score=0.15,
    )
    deps = make_deps([low_hit], min_score=0.30)

    async def mock_retrieve(*args: Any, **kwargs: Any) -> list[Hit]:
        return [low_hit]

    monkeypatch.setattr("techradar.rag.answer.retrieve", mock_retrieve)
    return deps


@pytest.fixture
def deps_hits(monkeypatch: pytest.MonkeyPatch) -> RagDeps:
    deps = make_deps(HITS)

    async def mock_retrieve(*args: Any, **kwargs: Any) -> list[Hit]:
        return HITS

    monkeypatch.setattr("techradar.rag.answer.retrieve", mock_retrieve)
    return deps


@pytest.fixture
def deps_hits_unverified(monkeypatch: pytest.MonkeyPatch) -> RagDeps:
    unv_hits = [
        Hit(
            chunk_id=1,
            doc_path="notes/unv.md",
            title="Unverified Doc",
            heading_path=[],
            text="Unverified draft content.",
            doc_kind="user",
            verified=False,
            generated=False,
            score=0.90,
        )
    ]
    deps = make_deps(unv_hits)

    async def mock_retrieve(*args: Any, **kwargs: Any) -> list[Hit]:
        return unv_hits

    monkeypatch.setattr("techradar.rag.answer.retrieve", mock_retrieve)
    return deps


async def test_not_found_when_no_hits(deps_no_hits: RagDeps) -> None:
    a = await answer_question("What is the repo rate?", deps_no_hits)
    assert (a.status, a.text) == ("not_found", NOT_FOUND)


async def test_not_found_below_min_score(deps_low_scores: RagDeps) -> None:
    assert (await answer_question("x?", deps_low_scores)).status == "not_found"


async def test_answered_with_valid_citations(deps_hits: RagDeps) -> None:
    resp = '{"answer": "It stayed at 6.5% [C1].", "citations": ["C1"]}'
    deps_hits.completer = FakeCompleter([resp])
    a = await answer_question("repo rate?", deps_hits)
    assert a.status == "answered"
    assert len(a.citations) == 1
    assert a.citations[0].doc_path == HITS[0].doc_path
    assert a.citations[0].n == 1
    assert a.citations[0].verified is True


async def test_citation_out_of_range_needs_review(deps_hits: RagDeps) -> None:
    deps_hits.completer = FakeCompleter(['{"answer": "Yes [C9].", "citations": ["C9"]}'])
    a = await answer_question("q?", deps_hits)
    assert (a.status, a.flags) == ("needs_review", ["bad_citation"])


async def test_answer_without_marker_needs_review(deps_hits: RagDeps) -> None:
    deps_hits.completer = FakeCompleter(['{"answer": "It is 5.5%.", "citations": []}'])
    assert (await answer_question("q?", deps_hits)).status == "needs_review"


async def test_link_in_answer_needs_review(deps_hits: RagDeps) -> None:
    bad = '{"answer": "See https://evil.example [C1]", "citations": ["C1"]}'
    deps_hits.completer = FakeCompleter([bad, bad])
    a = await answer_question("q?", deps_hits)
    assert a.status == "needs_review"
    assert a.flags == ["invalid_output"]


async def test_used_unverified_flag(deps_hits_unverified: RagDeps) -> None:
    resp = '{"answer": "Claim [C1].", "citations": ["C1"]}'
    deps_hits_unverified.completer = FakeCompleter([resp])
    assert (await answer_question("q?", deps_hits_unverified)).used_unverified is True


async def test_question_too_long(deps_hits: RagDeps) -> None:
    assert (await answer_question("x" * 501, deps_hits)).flags == ["too_long"]
