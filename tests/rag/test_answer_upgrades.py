"""answer_question with doc scope, a model role, query rewriting and neighbour expansion."""

from typing import Any

import pytest

from techradar.llm.roles import Role
from techradar.rag import answer as answer_mod
from techradar.rag.answer import answer_question
from techradar.rag.retrieve import Hit, RagDeps
from techradar.settings import Settings
from tests.fakes import FakeCompleter, FakeEmbedder, FakeReranker

ANSWER = '{"answer": "It stayed at 6.5% [C1].", "citations": ["C1"]}'


def hit(cid: int, text: str = "RBI kept the repo rate at 6.5%.", ordinal: int = 5) -> Hit:
    return Hit(
        chunk_id=cid,
        doc_path="library/7/book.md",
        title="Indian Economy",
        heading_path=["Money"],
        text=text,
        doc_kind="library",
        verified=True,
        generated=False,
        score=0.9,
        doc_id=7,
        ordinal=ordinal,
    )


class Spy:
    def __init__(self, result: list[Hit]) -> None:
        self.result = result
        self.calls: list[tuple[Any, dict[str, Any]]] = []

    async def __call__(self, queries: Any, deps: RagDeps, *args: Any, **kwargs: Any) -> list[Hit]:
        self.calls.append((queries, kwargs))
        return self.result


@pytest.fixture
def deps() -> RagDeps:
    return RagDeps(
        ro_session_factory=None,  # type: ignore[arg-type]  # retrieval is mocked in these tests
        completer=FakeCompleter([]),
        embedder=FakeEmbedder(dim=1024),
        reranker=FakeReranker(),
        settings=Settings(telegram_owner_chat_id=1, rag_min_score=0.30, max_question_chars=500),
    )


async def test_doc_id_is_passed_to_retrieve(monkeypatch, deps):
    spy = Spy([hit(1)])
    monkeypatch.setattr(answer_mod, "retrieve", spy)
    deps.completer = FakeCompleter([ANSWER])
    a = await answer_question("repo rate?", deps, doc_id=7)
    assert a.status == "answered"
    assert spy.calls[0][1]["doc_id"] == 7


async def test_default_has_no_scope_and_no_extra_model_calls(monkeypatch, deps):
    spy = Spy([hit(1)])
    monkeypatch.setattr(answer_mod, "retrieve", spy)
    deps.completer = FakeCompleter([ANSWER])
    await answer_question("repo rate?", deps)
    assert spy.calls[0][1].get("doc_id") is None
    assert len(deps.completer.calls) == 1


async def test_role_selects_the_answer_model(monkeypatch, deps):
    monkeypatch.setattr(answer_mod, "retrieve", Spy([hit(1)]))
    deps.completer = FakeCompleter([ANSWER])
    await answer_question("repo rate?", deps, role=Role.NIGHT)
    assert deps.completer.calls[0]["role"] == Role.NIGHT


async def test_default_role_is_worker(monkeypatch, deps):
    monkeypatch.setattr(answer_mod, "retrieve", Spy([hit(1)]))
    deps.completer = FakeCompleter([ANSWER])
    await answer_question("repo rate?", deps)
    assert deps.completer.calls[0]["role"] == Role.WORKER


async def test_night_role_keeps_the_citation_checks(monkeypatch, deps):
    monkeypatch.setattr(answer_mod, "retrieve", Spy([hit(1)]))
    deps.completer = FakeCompleter(['{"answer": "Yes [C9].", "citations": ["C9"]}'])
    a = await answer_question("q?", deps, role=Role.NIGHT)
    assert (a.status, a.flags) == ("needs_review", ["bad_citation"])


async def test_rewrite_runs_every_query_through_retrieve_multi(monkeypatch, deps):
    single = Spy([])
    multi = Spy([hit(1)])
    monkeypatch.setattr(answer_mod, "retrieve", single)
    monkeypatch.setattr(answer_mod, "retrieve_multi", multi)
    deps.completer = FakeCompleter(['{"queries": ["cash reserve ratio"]}', ANSWER])
    a = await answer_question("What is CRR?", deps, doc_id=7, rewrite=True)
    assert a.status == "answered"
    assert multi.calls[0][0] == ["What is CRR?", "cash reserve ratio"]
    assert multi.calls[0][1]["doc_id"] == 7
    assert single.calls == []
    assert deps.completer.calls[0]["role"] == Role.WORKER  # the rewrite
    assert deps.completer.calls[1]["role"] == Role.WORKER  # the answer


async def test_rewrite_uses_worker_even_when_the_answer_uses_night(monkeypatch, deps):
    monkeypatch.setattr(answer_mod, "retrieve_multi", Spy([hit(1)]))
    monkeypatch.setattr(answer_mod, "retrieve", Spy([hit(1)]))
    deps.completer = FakeCompleter(['{"queries": ["crr"]}', ANSWER])
    await answer_question("What is CRR?", deps, rewrite=True, role=Role.NIGHT)
    assert [c["role"] for c in deps.completer.calls] == [Role.WORKER, Role.NIGHT]


async def test_failed_rewrite_falls_back_to_plain_retrieve(monkeypatch, deps):
    single = Spy([hit(1)])
    multi = Spy([])
    monkeypatch.setattr(answer_mod, "retrieve", single)
    monkeypatch.setattr(answer_mod, "retrieve_multi", multi)
    deps.completer = FakeCompleter(["junk", "junk", ANSWER])
    a = await answer_question("What is CRR?", deps, rewrite=True)
    assert a.status == "answered"
    assert single.calls and not multi.calls


async def test_expand_adds_neighbour_excerpts_to_the_prompt(monkeypatch, deps):
    anchor = hit(1)
    before = hit(2, "Earlier context sentence.", ordinal=4)
    after = hit(3, "Later context sentence.", ordinal=6)
    monkeypatch.setattr(answer_mod, "retrieve", Spy([anchor]))

    async def fake_load(d: RagDeps, hits: list[Hit], f: Any = None) -> Any:
        return lambda h: (before, after)

    monkeypatch.setattr(answer_mod, "load_neighbors", fake_load)
    deps.completer = FakeCompleter(['{"answer": "Later says so [C3].", "citations": ["C3"]}'])
    a = await answer_question("repo rate?", deps, expand=True)
    prompt = deps.completer.calls[0]["messages"][1]["content"]
    assert prompt.index("Earlier context") < prompt.index("6.5%") < prompt.index("Later context")
    assert a.status == "answered"
    assert [c.n for c in a.citations] == [3]


async def test_expand_does_not_change_the_not_found_decision(monkeypatch, deps):
    low = hit(1).model_copy(update={"score": 0.1})
    monkeypatch.setattr(answer_mod, "retrieve", Spy([low]))

    async def boom(*args: Any, **kw: Any) -> Any:
        raise AssertionError("must not load neighbours when nothing is relevant")

    monkeypatch.setattr(answer_mod, "load_neighbors", boom)
    a = await answer_question("q?", deps, expand=True)
    assert a.status == "not_found"


async def test_expand_off_never_loads_neighbours(monkeypatch, deps):
    monkeypatch.setattr(answer_mod, "retrieve", Spy([hit(1)]))

    async def boom(*args: Any, **kw: Any) -> Any:
        raise AssertionError("neighbours loaded with expand=False")

    monkeypatch.setattr(answer_mod, "load_neighbors", boom)
    deps.completer = FakeCompleter([ANSWER])
    assert (await answer_question("q?", deps)).status == "answered"


async def test_expanded_context_stays_within_the_excerpt_cap(monkeypatch, deps):
    anchors = [hit(i, f"Anchor {i}.", ordinal=i * 10) for i in range(1, 7)]
    monkeypatch.setattr(answer_mod, "retrieve", Spy(anchors))

    async def fake_load(d: RagDeps, hits: list[Hit], f: Any = None) -> Any:
        return lambda h: (hit(100 + h.chunk_id, "b", ordinal=1), hit(200 + h.chunk_id, "a", 2))

    monkeypatch.setattr(answer_mod, "load_neighbors", fake_load)
    deps.completer = FakeCompleter([ANSWER])
    await answer_question("q?", deps, expand=True)
    prompt = deps.completer.calls[0]["messages"][1]["content"]
    assert "[C6]" in prompt and "[C7]" not in prompt
