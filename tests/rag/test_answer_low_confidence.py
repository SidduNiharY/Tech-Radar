"""A not_found answer says when the best hit was close to the cut-off (hard question)."""

from typing import Any

import pytest

from techradar.rag import answer as answer_mod
from techradar.rag.answer import LOW_CONFIDENCE, answer_question
from techradar.rag.retrieve import Hit, RagDeps
from techradar.settings import Settings
from tests.fakes import FakeCompleter, FakeEmbedder, FakeReranker


def _hit(score: float) -> Hit:
    return Hit(
        chunk_id=1,
        doc_path="library/7/b.md",
        title="T",
        heading_path=[],
        text="text",
        doc_kind="library",
        verified=True,
        generated=False,
        score=score,
        doc_id=7,
    )


def _deps() -> RagDeps:
    return RagDeps(
        ro_session_factory=None,  # type: ignore[arg-type]  # retrieval is mocked
        completer=FakeCompleter([]),
        embedder=FakeEmbedder(dim=1024),
        reranker=FakeReranker(),
        settings=Settings(telegram_owner_chat_id=1, rag_min_score=0.30, max_question_chars=500),
    )


def _patch(monkeypatch: pytest.MonkeyPatch, hits: list[Hit]) -> None:
    async def fake(*_a: Any, **_k: Any) -> list[Hit]:
        return hits

    monkeypatch.setattr(answer_mod, "retrieve", fake)


@pytest.mark.parametrize(("score", "flagged"), [(0.25, True), (0.20, True), (0.15, False)])
async def test_not_found_near_the_cutoff_is_low_confidence(monkeypatch, score, flagged):
    _patch(monkeypatch, [_hit(score)])
    a = await answer_question("x?", _deps())
    assert a.status == "not_found"
    assert (LOW_CONFIDENCE in a.flags) is flagged


async def test_no_hits_is_plain_not_found(monkeypatch):
    _patch(monkeypatch, [])
    a = await answer_question("x?", _deps())
    assert (a.status, a.flags) == ("not_found", [])
