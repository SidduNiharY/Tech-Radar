"""Book asks and hard questions deferred to the night model (Phase 2c Task 8).

SEC: SEC-26, SEC-37, SEC-38, SEC-41.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any

import pytest

from techradar.db.models import Answer as AnswerModel
from techradar.db.models import Outbox
from techradar.llm.roles import Role
from techradar.rag.answer import LOW_CONFIDENCE, NOT_FOUND, Answer, Citation
from techradar.worker import ask_flow
from techradar.worker.ask_flow import (
    DEFER_REPLY,
    run_ask,
    run_night_ask,
    valid_ask_args,
)

OWNER = 1
GROUP = -100


def _answered() -> Answer:
    cite = Citation(n=1, doc_path="library/7/b.md", title="Book", heading="Money", verified=True)
    return Answer(
        text="It stayed at 6.5% [C1].",
        citations=[cite],
        status="answered",
        used_unverified=False,
        flags=[],
    )


def _review(*flags: str) -> Answer:
    return Answer(
        text="x", citations=[], status="needs_review", used_unverified=False, flags=list(flags)
    )


def _not_found(*flags: str) -> Answer:
    return Answer(
        text=NOT_FOUND, citations=[], status="not_found", used_unverified=False, flags=list(flags)
    )


class Script:
    """answer_question stand-in: returns the scripted answers in order and records the calls."""

    def __init__(self, *answers: Answer) -> None:
        self.answers = list(answers)
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def __call__(self, question: str, deps: Any, **kwargs: Any) -> Answer:
        self.calls.append((question, kwargs))
        return self.answers.pop(0)


class FakeSession:
    def __init__(self) -> None:
        self.added: list[Any] = []
        self.commits = 0

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        for n, obj in enumerate(self.added, 1):
            if getattr(obj, "id", None) is None:
                obj.id = n

    async def commit(self) -> None:
        self.commits += 1

    async def execute(self, stmt: Any) -> Any:  # Phase 11: the follow-up lookup finds nothing
        class _Result:
            def scalar_one_or_none(self) -> None:
                return None

        return _Result()


class Env:
    def __init__(self) -> None:
        self.session = FakeSession()
        self.deferred: list[tuple[str, int | None]] = []

    def factory(self):
        @asynccontextmanager
        async def cm():
            yield self.session

        return cm

    async def defer(self, question: str, doc_id: int | None) -> None:
        self.deferred.append((question, doc_id))

    @property
    def outbox(self) -> list[Outbox]:
        return [o for o in self.session.added if isinstance(o, Outbox)]

    @property
    def answers(self) -> list[AnswerModel]:
        return [o for o in self.session.added if isinstance(o, AnswerModel)]


@pytest.fixture
def env() -> Env:
    return Env()


def _deps() -> Any:
    return SimpleNamespace(settings=SimpleNamespace(max_question_chars=500))


async def _run(env: Env, script: Script, monkeypatch, *, chat=OWNER, doc_id=None, q="What is CRR?"):
    monkeypatch.setattr(ask_flow, "answer_question", script)
    await run_ask(
        q,
        chat_id=chat,
        doc_id=doc_id,
        deps=_deps(),
        session_factory=env.factory(),
        owner_chat_id=OWNER,
        defer_night=env.defer,
    )


# --- a normal answer ---------------------------------------------------------------


async def test_a_plain_ask_is_answered_and_sent(env, monkeypatch) -> None:
    script = Script(_answered())
    await _run(env, script, monkeypatch)
    assert len(script.calls) == 1
    assert script.calls[0][1].get("doc_id") is None
    assert not script.calls[0][1].get("require_doc_id")
    assert [o.purpose for o in env.outbox] == ["answer"]
    assert env.outbox[0].chat_id == OWNER
    aid = env.answers[0].id
    assert env.outbox[0].buttons[0] == [{"text": "Save to vault", "data": f"save_answer:{aid}"}]
    assert env.outbox[0].buttons[1][0] == {"text": "👍", "data": f"fb_up:2:{aid}"}  # Phase 11
    assert len(env.answers) == 1 and env.session.commits == 2  # the ask note, then the answer
    assert env.deferred == []


async def test_a_book_ask_is_scoped_and_requires_the_doc(env, monkeypatch) -> None:
    script = Script(_answered())
    await _run(env, script, monkeypatch, doc_id=7)
    kw = script.calls[0][1]
    assert kw["doc_id"] == 7 and kw["require_doc_id"] is True
    assert kw.get("role", Role.WORKER) is Role.WORKER


# --- hard questions ------------------------------------------------------------------


async def test_needs_review_twice_defers_to_night(env, monkeypatch) -> None:
    script = Script(_review("bad_citation"), _review("bad_citation"))
    await _run(env, script, monkeypatch, doc_id=7, q="Explain the Taylor rule in this book")
    assert len(script.calls) == 2
    assert script.calls[1][1]["rewrite"] is True and script.calls[1][1]["expand"] is True
    assert env.deferred == [("Explain the Taylor rule in this book", 7)]
    assert [(o.purpose, o.text) for o in env.outbox] == [("answer_deferred", DEFER_REPLY)]
    assert env.answers == []
    assert DEFER_REPLY == "I'll answer this one tonight with the bigger model."


async def test_second_try_can_rescue_a_needs_review(env, monkeypatch) -> None:
    script = Script(_review("bad_citation"), _answered())
    await _run(env, script, monkeypatch)
    assert env.deferred == []
    assert [o.purpose for o in env.outbox] == ["answer"]


async def test_low_confidence_not_found_defers_at_once(env, monkeypatch) -> None:
    script = Script(_not_found(LOW_CONFIDENCE))
    await _run(env, script, monkeypatch)
    assert len(script.calls) == 1
    assert env.deferred == [("What is CRR?", None)]
    assert [o.text for o in env.outbox] == [DEFER_REPLY]


async def test_plain_not_found_is_delivered_not_deferred(env, monkeypatch) -> None:
    await _run(env, Script(_not_found()), monkeypatch)
    assert env.deferred == []
    assert [o.text for o in env.outbox] == [NOT_FOUND]


async def test_too_long_is_delivered_not_retried_or_deferred(env, monkeypatch) -> None:
    script = Script(_review("too_long"))
    await _run(env, script, monkeypatch)
    assert len(script.calls) == 1 and env.deferred == []
    assert env.outbox[0].purpose == "answer"


async def test_a_study_group_never_gets_a_night_deferral(env, monkeypatch) -> None:
    script = Script(_review("bad_citation"), _review("bad_citation"))
    await _run(env, script, monkeypatch, chat=GROUP)
    assert env.deferred == []
    assert [o.chat_id for o in env.outbox] == [GROUP]
    assert "couldn't answer" in env.outbox[0].text


async def test_failed_deferral_falls_back_to_the_plain_answer(env, monkeypatch) -> None:
    async def boom(_q: str, _d: int | None) -> None:
        raise RuntimeError("queue down")

    env.defer = boom  # type: ignore[method-assign]
    await _run(env, Script(_not_found(LOW_CONFIDENCE)), monkeypatch)
    assert [o.purpose for o in env.outbox] == ["answer"]


# --- argument validation ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("question", "doc_id", "ok"),
    [
        ("What is CRR?", None, True),
        ("What is CRR?", 7, True),
        ("x" * 500, None, True),
        ("x" * 501, None, False),
        ("", None, False),
        ("   ", None, False),
        (None, None, False),
        (5, None, False),
        ("q", 0, False),
        ("q", -3, False),
        ("q", True, False),
        ("q", "7", False),
        ("q", 7.0, False),
        ("q", 10**12, False),
    ],
)
def test_valid_ask_args(question, doc_id, ok) -> None:
    assert valid_ask_args(question, doc_id, 500) is ok


async def test_run_ask_drops_invalid_arguments(env, monkeypatch) -> None:
    script = Script()
    await _run(env, script, monkeypatch, doc_id=-1)
    await _run(env, script, monkeypatch, q="x" * 501)
    assert script.calls == [] and env.outbox == [] and env.deferred == []


# --- the night answer --------------------------------------------------------------------


async def _night(env: Env, script: Script, monkeypatch, **kw):
    monkeypatch.setattr(ask_flow, "answer_question", script)
    args: dict[str, Any] = {"question": "Explain the Taylor rule", "doc_id": 7}
    args.update(kw)
    await run_night_ask(
        args["question"],
        doc_id=args["doc_id"],
        deps=_deps(),
        session_factory=env.factory(),
        owner_chat_id=OWNER,
    )


async def test_night_answer_uses_the_night_model_and_goes_to_the_owner(env, monkeypatch) -> None:
    script = Script(_answered())
    await _night(env, script, monkeypatch)
    kw = script.calls[0][1]
    assert kw["role"] is Role.NIGHT and kw["doc_id"] == 7 and kw["require_doc_id"] is True
    assert kw["rewrite"] is True and kw["expand"] is True
    assert [(o.chat_id, o.purpose) for o in env.outbox] == [(OWNER, "answer")]
    assert len(env.answers) == 1 and env.answers[0].chat_id == OWNER


async def test_night_answer_unscoped_does_not_require_a_doc(env, monkeypatch) -> None:
    script = Script(_answered())
    await _night(env, script, monkeypatch, doc_id=None)
    assert script.calls[0][1]["doc_id"] is None and script.calls[0][1]["require_doc_id"] is False


async def test_night_answer_that_fails_the_checks_is_not_sent_raw(env, monkeypatch) -> None:
    script = Script(_review("bad_citation"))
    await _night(env, script, monkeypatch)
    (msg,) = env.outbox
    assert msg.text == "I couldn't answer that safely. (bad_citation)"
    assert env.deferred == []  # the night path never defers again


async def test_night_job_rejects_bad_arguments(env, monkeypatch) -> None:
    script = Script()
    await _night(env, script, monkeypatch, doc_id=0)
    await _night(env, script, monkeypatch, question="x" * 501)
    assert script.calls == [] and env.outbox == []


# --- the job wiring ------------------------------------------------------------------------


def _wire(monkeypatch, *, hour: int) -> dict[str, Any]:
    """Settings, clock and collaborators for the real `ask_night` task; returns what they saw."""
    from datetime import UTC, datetime

    from techradar.night import window
    from techradar.worker import tasks

    seen: dict[str, Any] = {"deferred": [], "ran": []}
    settings = SimpleNamespace(
        night_start="01:00", night_end="05:00", tz="UTC", telegram_owner_chat_id=OWNER,
        max_question_chars=500,
    )  # fmt: skip
    monkeypatch.setattr(tasks, "_get_settings", lambda: settings)
    monkeypatch.setattr("techradar.settings.get_settings", lambda: settings)
    monkeypatch.setattr(window, "_utc_now", lambda: datetime(2026, 11, 14, hour, 0, tzinfo=UTC))

    async def free() -> list[str]:
        return []

    monkeypatch.setattr(window, "_default_free", free)

    def default_defer(task_name: str):
        async def defer(when: Any, kwargs: dict[str, Any]) -> None:
            seen["deferred"].append((task_name, when, kwargs))

        return defer

    monkeypatch.setattr(window, "_default_defer", default_defer)
    monkeypatch.setattr(tasks, "get_rag_deps", lambda: "deps")
    monkeypatch.setattr(tasks, "make_session_factory", lambda *_a, **_k: "factory")

    async def fake_night(question: str, **kw: Any) -> None:
        seen["ran"].append((question, kw))

    monkeypatch.setattr(tasks, "run_night_ask", fake_night)
    return seen


def test_ask_night_is_a_night_only_night_queue_job() -> None:
    from techradar.worker.tasks import ask_job, ask_night

    assert (ask_night.name, ask_night.queue) == ("ask_night", "night")
    assert (ask_job.name, ask_job.queue) == ("ask", "llm")
    assert hasattr(ask_night.func, "__wrapped__")  # wrapped by night_only


async def test_ask_night_outside_the_window_is_deferred_with_its_arguments(monkeypatch) -> None:
    from techradar.worker.tasks import ask_night

    seen = _wire(monkeypatch, hour=12)
    await ask_night.func(question="q?", doc_id=7)
    assert seen["ran"] == []
    ((name, _when, kwargs),) = seen["deferred"]
    assert (name, kwargs) == ("ask_night", {"question": "q?", "doc_id": 7})


async def test_ask_night_in_the_window_answers_to_the_owner_from_settings(monkeypatch) -> None:
    from techradar.worker.tasks import ask_night

    seen = _wire(monkeypatch, hour=2)
    await ask_night.func(question="q?", doc_id=7)
    assert seen["deferred"] == []
    ((question, kw),) = seen["ran"]
    assert question == "q?"
    assert kw["doc_id"] == 7 and kw["owner_chat_id"] == OWNER
    assert kw["deps"] == "deps" and kw["session_factory"] == "factory"


def test_ask_night_takes_no_chat_id_from_the_job() -> None:
    import inspect

    from techradar.worker.tasks import ask_night

    wrapped = ask_night.func.__wrapped__  # type: ignore[attr-defined]
    assert list(inspect.signature(wrapped).parameters) == ["question", "doc_id"]


async def test_ask_job_passes_the_book_and_validates(monkeypatch) -> None:
    from techradar.worker import tasks

    seen = _wire(monkeypatch, hour=12)
    calls: list[tuple[str, dict[str, Any]]] = []

    async def fake_run(question: str, **kw: Any) -> None:
        calls.append((question, kw))

    monkeypatch.setattr(tasks, "run_ask", fake_run)
    await tasks.ask_job(chat_id=OWNER, question="q?", doc_id=7)
    await tasks.ask_job(chat_id=OWNER, question="q?")
    ((q1, k1), (_q2, k2)) = calls
    assert (q1, k1["chat_id"], k1["doc_id"], k1["owner_chat_id"]) == ("q?", OWNER, 7, OWNER)
    assert k2["doc_id"] is None
    assert callable(k1["defer_night"])
    assert seen["ran"] == []  # validation itself is run_ask's (tested above)


def _clock(monkeypatch, hour: int) -> None:
    from datetime import UTC, datetime

    from techradar.worker import tasks

    class Clock(datetime):
        @classmethod
        def now(cls, tz: Any = None) -> datetime:
            return datetime(2026, 11, 14, hour, 0, tzinfo=UTC).astimezone(tz)

    monkeypatch.setattr(tasks, "datetime", Clock)


async def test_deferral_schedules_the_next_window_start(monkeypatch) -> None:
    from datetime import UTC, datetime

    from techradar.worker import tasks

    _wire(monkeypatch, hour=12)
    _clock(monkeypatch, 12)
    configured: list[dict[str, Any]] = []
    deferred: list[dict[str, Any]] = []

    class Job:
        def configure(self, **options: Any):
            configured.append(options)
            return self

        async def defer_async(self, **kwargs: Any) -> None:
            deferred.append(kwargs)

    monkeypatch.setattr(tasks, "ask_night", Job())
    await tasks._defer_ask_night("q?", 7)
    assert configured == [{"schedule_at": datetime(2026, 11, 15, 1, 0, tzinfo=UTC)}]
    assert deferred == [{"question": "q?", "doc_id": 7}]
    # inside the window it runs as soon as a worker is free
    configured.clear()
    _clock(monkeypatch, 2)
    await tasks._defer_ask_night("q?", None)
    assert configured == [{}]
