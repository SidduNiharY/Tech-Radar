"""Test helpers for the night pages: fake excerpts and a RagDeps with fakes (not a conftest)."""

from __future__ import annotations

from typing import Any

import pytest

from techradar.rag.retrieve import Hit, RagDeps
from techradar.settings import Settings
from tests.fakes import FakeCompleter, FakeEmbedder, FakeReranker


def make_hit(
    n: int,
    *,
    kind: str = "library",
    verified: bool | None = None,
    flagged: bool = False,
    score: float = 0.9,
    text: str | None = None,
    title: str | None = None,
) -> Hit:
    return Hit(
        chunk_id=n,
        doc_path=f"library/book-{n}.md",
        title=title or f"Source {n}",
        heading_path=["Part"],
        text=text or f"Excerpt number {n} about the topic.",
        doc_kind=kind,
        verified=verified,
        generated=False,
        score=score,
        flagged=flagged,
    )


def make_deps(completer: FakeCompleter | None = None, **settings: Any) -> RagDeps:
    class _NoSession:
        def __call__(self) -> Any:  # never used: retrieve is patched
            raise AssertionError("the database must not be touched in this test")

    return RagDeps(
        ro_session_factory=_NoSession(),  # type: ignore[arg-type]
        completer=completer or FakeCompleter([]),
        embedder=FakeEmbedder(dim=4),
        reranker=FakeReranker(),
        settings=Settings(telegram_owner_chat_id=1, **settings),
    )


def patch_retrieve(monkeypatch: pytest.MonkeyPatch, hits: list[Hit]) -> list[dict[str, Any]]:
    """Make grounded retrieval return `hits`; the list records each call's query and k_final."""
    calls: list[dict[str, Any]] = []

    async def fake_retrieve(question: str, deps: RagDeps, *args: Any, **kwargs: Any) -> list[Hit]:
        calls.append({"query": question, "k_final": deps.settings.rag_k_final})
        return hits

    monkeypatch.setattr("techradar.night.grounding.retrieve", fake_retrieve)
    return calls
