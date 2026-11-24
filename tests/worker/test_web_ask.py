"""Web asks (Phase 4 Task 2): the `ask` job fills the pending row the API created.

SEC: SEC-41. The job trusts nothing it is given: the row must exist, still be pending and
hold the same question, and a finished answer is never overwritten (a replayed job is a
no-op). Web answers never go to Telegram and are never deferred to the night model.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any

import pytest

from techradar.db.models import Answer as AnswerModel
from techradar.rag.answer import Answer, Citation
from techradar.rag.retrieve import RetrieveFilters
from techradar.worker import ask_flow
from techradar.worker.ask_flow import run_web_ask


class Result:
    def __init__(self, value: Any) -> None:
        self.value = value

    def scalar_one_or_none(self) -> Any:
        return self.value


class Session:
    """Records statements; `select` returns the scripted row."""

    def __init__(self, row: AnswerModel | None) -> None:
        self.row = row
        self.updates: list[dict[str, Any]] = []
        self.added: list[Any] = []
        self.commits = 0

    async def execute(self, stmt: Any) -> Result:
        if stmt.is_select:
            return Result(self.row)
        compiled = stmt.compile()
        self.updates.append({"sql": str(compiled), "params": compiled.params})
        return Result(1)

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    async def commit(self) -> None:
        self.commits += 1


def _factory(session: Session):
    @asynccontextmanager
    async def cm():
        yield session

    return cm


def _deps() -> Any:
    return SimpleNamespace(settings=SimpleNamespace(max_question_chars=500))


def _pending(question: str = "What did RBI decide?") -> AnswerModel:
    row = AnswerModel(chat_id=1, question=question, text="", status="pending")
    row.id = 41
    return row


def _answered() -> Answer:
    cite = Citation(n=1, doc_path="wiki/rbi.md", title="RBI", heading="Rates", verified=True)
    return Answer(
        text="Held at 5.5% [C1].", citations=[cite], status="answered", used_unverified=False,
        flags=[],
    )  # fmt: skip


@pytest.fixture
def script(monkeypatch):
    calls: list[tuple[str, dict[str, Any]]] = []
    answers: list[Answer] = []

    async def fake(question: str, deps: Any, **kw: Any) -> Answer:
        calls.append((question, kw))
        return answers.pop(0)

    monkeypatch.setattr(ask_flow, "answer_question", fake)
    return SimpleNamespace(calls=calls, answers=answers)


async def test_web_ask_fills_the_pending_row(script) -> None:
    script.answers.append(_answered())
    session = Session(_pending())
    await run_web_ask(
        "What did RBI decide?", answer_id=41, doc_id=None, verified_only=False,
        deps=_deps(), session_factory=_factory(session),
    )  # fmt: skip
    [update] = session.updates
    assert "status = :status_1" in update["sql"] or "answers.status =" in update["sql"]
    assert update["params"]["status"] == "answered"
    assert update["params"]["text"] == "Held at 5.5% [C1]."
    assert update["params"]["citations"][0]["doc_path"] == "wiki/rbi.md"
    assert "pending" in update["params"].values()  # only a still-pending row is written
    assert session.added == []  # no outbox message: the web polls
    assert session.commits == 1


async def test_web_ask_passes_verified_only_as_a_filter(script) -> None:
    script.answers.append(_answered())
    await run_web_ask(
        "What did RBI decide?", answer_id=41, doc_id=None, verified_only=True,
        deps=_deps(), session_factory=_factory(Session(_pending())),
    )  # fmt: skip
    f = script.calls[0][1]["f"]
    assert isinstance(f, RetrieveFilters) and f.verified_only is True


@pytest.mark.parametrize(
    "row",
    [None, _pending("A different question?")],
    ids=["no-pending-row", "other-question"],
)
async def test_web_ask_without_its_pending_row_does_nothing(script, row) -> None:
    session = Session(row)
    await run_web_ask(
        "What did RBI decide?", answer_id=41, doc_id=None, verified_only=False,
        deps=_deps(), session_factory=_factory(session),
    )  # fmt: skip
    assert script.calls == [] and session.updates == []


@pytest.mark.parametrize("answer_id", [0, -1, 2**63, "41", None])
async def test_web_ask_refuses_a_bad_row_id(script, answer_id) -> None:
    session = Session(_pending())
    await run_web_ask(
        "What did RBI decide?", answer_id=answer_id, doc_id=None, verified_only=False,
        deps=_deps(), session_factory=_factory(session),
    )  # fmt: skip
    assert script.calls == [] and session.updates == []


async def test_web_ask_failure_marks_the_row_and_raises(monkeypatch) -> None:
    async def broken(question: str, deps: Any, **kw: Any) -> Answer:
        raise ConnectionError("ollama down")

    monkeypatch.setattr(ask_flow, "answer_question", broken)
    session = Session(_pending())
    with pytest.raises(ConnectionError):
        await run_web_ask(
            "What did RBI decide?", answer_id=41, doc_id=None, verified_only=False,
            deps=_deps(), session_factory=_factory(session),
        )  # fmt: skip
    [update] = session.updates
    assert update["params"]["status"] == "needs_review"
    assert update["params"]["flags"] == ["error"]
    assert update["params"]["text"] == ""


async def test_ask_job_with_an_answer_row_runs_the_web_path(monkeypatch) -> None:
    from techradar.worker import tasks

    seen: list[tuple[str, dict[str, Any]]] = []

    async def fake_web(question: str, **kw: Any) -> None:
        seen.append((question, kw))

    async def no_chat_ask(*_a: Any, **_k: Any) -> None:
        raise AssertionError("the Telegram path must not run")

    monkeypatch.setattr(tasks, "run_web_ask", fake_web)
    monkeypatch.setattr(tasks, "run_ask", no_chat_ask)
    monkeypatch.setattr(tasks, "get_rag_deps", lambda: "deps")
    monkeypatch.setattr(tasks, "make_session_factory", lambda *_a, **_k: "factory")
    await tasks.ask_job(question="q?", answer_id=41)
    await tasks.ask_job(question="q?", answer_id=42, verified_only=True)
    assert [(q, k["answer_id"], k["verified_only"]) for q, k in seen] == [
        ("q?", 41, False),
        ("q?", 42, True),
    ]


async def test_ask_job_with_neither_chat_nor_row_is_dropped(monkeypatch) -> None:
    from techradar.worker import tasks

    async def boom(*_a: Any, **_k: Any) -> None:
        raise AssertionError("nothing may run")

    monkeypatch.setattr(tasks, "run_web_ask", boom)
    monkeypatch.setattr(tasks, "run_ask", boom)
    await tasks.ask_job(question="q?")
