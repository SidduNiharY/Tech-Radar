"""answer_question prompts always fit the 8,192-token context; the SEC-41 caps always hold."""

import re
from typing import Any

import pytest

from techradar.rag import answer as answer_mod
from techradar.rag.answer import ANSWER_SYSTEM, answer_question
from techradar.rag.budget import NUM_CTX, conservative_tokens
from techradar.rag.expand import MAX_CONTEXT_TOKENS, MAX_EXCERPTS, expand_with_neighbors
from techradar.rag.retrieve import Hit, RagDeps
from techradar.settings import Settings
from tests.fakes import FakeCompleter, FakeEmbedder, FakeReranker

ANSWER = '{"answer": "It says so [C1].", "citations": ["C1"]}'
INDIC = "भारतीय रिज़र्व बैंक ने रेपो दर को स्थिर रखा। "
MAX_CHUNK = 10_000
BLOBS = {
    "ocr_blob": "x" * MAX_CHUNK,
    "indic": (INDIC * 400)[:MAX_CHUNK],
    "words": ("word " * 4000)[:MAX_CHUNK],
}


def hit(cid: int, text: str, ordinal: int = 5, *, path: str = "library/7/book.md") -> Hit:
    return Hit(
        chunk_id=cid,
        doc_path=path,
        title="Indian Economy",
        heading_path=["Money"],
        text=text,
        doc_kind="library",
        verified=True,
        generated=False,
        score=0.9,
        doc_id=7,
        chapter_id=1,
        ordinal=ordinal,
    )


class Spy:
    def __init__(self, result: list[Hit]) -> None:
        self.result = result
        self.calls: list[Any] = []

    async def __call__(self, *args: Any, **kwargs: Any) -> list[Hit]:
        self.calls.append((args, kwargs))
        return self.result


@pytest.fixture
def deps() -> RagDeps:
    return RagDeps(
        ro_session_factory=None,  # type: ignore[arg-type]  # retrieval is mocked
        completer=FakeCompleter([ANSWER]),
        embedder=FakeEmbedder(dim=1024),
        reranker=FakeReranker(),
        settings=Settings(telegram_owner_chat_id=1, rag_min_score=0.30, max_question_chars=500),
    )


def _sent(deps: RagDeps) -> tuple[str, str, int]:
    call = deps.completer.calls[-1]  # type: ignore[attr-defined]
    system, user = (m["content"] for m in call["messages"])
    return system, user, call["max_tokens"]


def _assert_fits_and_marked(deps: RagDeps) -> str:
    system, user, max_tokens = _sent(deps)
    assert conservative_tokens(system) + conservative_tokens(user) + max_tokens <= NUM_CTX
    assert system == ANSWER_SYSTEM
    assert re.match(r"<<UNTRUSTED [0-9a-f]+>>\n", user)
    return user


@pytest.mark.parametrize("kind", sorted(BLOBS))
@pytest.mark.parametrize("expand", [False, True])
async def test_full_answer_prompt_fits_for_worst_case_chunks(monkeypatch, deps, kind, expand):
    blob = BLOBS[kind]
    hits = [hit(i, blob, ordinal=10 * i, path=f"library/7/{i}.md") for i in range(1, 7)]
    monkeypatch.setattr(answer_mod, "retrieve", Spy(hits))

    async def fake_load(d: RagDeps, hs: list[Hit], f: Any = None) -> Any:
        return lambda h: (
            hit(100 + h.chunk_id, blob, h.ordinal - 1, path=h.doc_path),
            hit(200 + h.chunk_id, blob, h.ordinal + 1, path=h.doc_path),
        )

    monkeypatch.setattr(answer_mod, "load_neighbors", fake_load)
    question = (INDIC * 20)[:500] if kind == "indic" else "q" * 500
    a = await answer_question(question, deps, expand=expand)
    assert a.status == "answered"
    user = _assert_fits_and_marked(deps)
    assert "[C1]" in user  # the best hit is always sent, cut if it must be


async def test_oversized_hits_never_go_to_the_model_uncapped(monkeypatch, deps):
    # every hit alone is bigger than the expand cap: the old `or hits` sent all of them whole
    huge = [hit(i, f"{i}" * 40_000, ordinal=10 * i, path=f"library/7/{i}.md") for i in (1, 2, 3)]
    monkeypatch.setattr(answer_mod, "retrieve", Spy(huge))

    async def no_neighbours(d: RagDeps, hs: list[Hit], f: Any = None) -> Any:
        return lambda h: (None, None)

    monkeypatch.setattr(answer_mod, "load_neighbors", no_neighbours)
    await answer_question("q?", deps, expand=True)
    user = _assert_fits_and_marked(deps)
    assert "[C1]" in user and "[C2]" not in user
    assert "1" * 1000 in user  # the top hit, truncated
    assert "1" * 40_000 not in user and "2" * 100 not in user


async def test_without_expand_at_most_six_excerpts_are_sent(monkeypatch, deps):
    many = [hit(i, f"Short excerpt {i}.", ordinal=i) for i in range(1, 10)]
    monkeypatch.setattr(answer_mod, "retrieve", Spy(many))
    await answer_question("q?", deps)
    user = _assert_fits_and_marked(deps)
    assert f"[C{MAX_EXCERPTS}]" in user and f"[C{MAX_EXCERPTS + 1}]" not in user


async def test_huge_titles_and_headings_cannot_overflow(monkeypatch, deps):
    h = hit(1, "body").model_copy(update={"title": "T" * 50_000, "heading_path": ["H" * 50_000]})
    monkeypatch.setattr(answer_mod, "retrieve", Spy([h]))
    await answer_question("q?", deps)
    _assert_fits_and_marked(deps)


def test_expand_cap_is_within_sec41() -> None:
    assert MAX_CONTEXT_TOKENS <= 8000
    assert MAX_EXCERPTS == 6


def test_expand_counts_tokens_conservatively() -> None:
    blob = hit(1, "x" * MAX_CHUNK)  # one "word": words x 1.3 says 2 tokens
    small = hit(2, "a small hit", ordinal=20, path="library/7/other.md")
    out = expand_with_neighbors([blob, small], lambda _h: (None, None), max_tokens=3000)
    assert [h.chunk_id for h in out] == [2]


# --- doc scope checks (defence in depth) -------------------------------------------


async def test_require_doc_id_rejects_a_missing_scope(monkeypatch, deps):
    spy = Spy([hit(1, "body")])
    monkeypatch.setattr(answer_mod, "retrieve", spy)
    with pytest.raises(ValueError, match="doc_id"):
        await answer_question("q?", deps, require_doc_id=True)
    assert spy.calls == [] and deps.completer.calls == []  # type: ignore[attr-defined]
    a = await answer_question("q?", deps, doc_id=7, require_doc_id=True)
    assert a.status == "answered"


@pytest.mark.parametrize("bad", ["7", 7.0, True, [7]])
async def test_bad_doc_id_fails_before_the_rewrite_model_call(monkeypatch, deps, bad):
    monkeypatch.setattr(answer_mod, "retrieve", Spy([hit(1, "body")]))
    monkeypatch.setattr(answer_mod, "retrieve_multi", Spy([hit(1, "body")]))
    with pytest.raises(TypeError):
        await answer_question("q?", deps, doc_id=bad, rewrite=True)
    assert deps.completer.calls == []  # type: ignore[attr-defined]
