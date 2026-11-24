"""Phase 4 Task 2 routes without a database: fakes for the session and the job queue.

The database side is in test_routes.py (marker `db`). SEC: SEC-18, SEC-27, SEC-41, SEC-54.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from starlette.testclient import TestClient

from techradar.api import deps
from techradar.api.main import create_app
from techradar.api.resources import ollama_ps, parse_meminfo, parse_ollama_ps
from techradar.api.routes.ask import answer_status
from techradar.api.routes.quiz import quiz_question
from techradar.api.routes.today import today_item
from techradar.api.schemas import UserSettings
from techradar.db.models import Answer as AnswerRow
from techradar.user_settings import default_settings, merge_settings
from tests.api.conftest import AUTH, FakeDefer, FakeSession, use_fakes


@pytest.fixture
def fakes(settings) -> tuple[TestClient, FakeSession, FakeDefer]:
    app = create_app(settings)
    session, defer = FakeSession(), FakeDefer()
    use_fakes(app, session, defer)
    return TestClient(app), session, defer


def _answer(status: str, **kw: object) -> AnswerRow:
    row = AnswerRow(
        chat_id=1, question="What did RBI decide?", text=kw.pop("text", ""), status=status, **kw
    )
    row.id = 7
    row.created_at = datetime(2026, 11, 22, tzinfo=UTC)
    return row


# --- ask -------------------------------------------------------------------------------


def test_ask_creates_pending_and_defers(fakes) -> None:
    client, session, defer = fakes
    r = client.post("/v1/ask", headers=AUTH, json={"question": "What did RBI decide?"})
    assert r.status_code == 200
    [row] = session.added
    assert (row.status, row.text, row.question) == ("pending", "", "What did RBI decide?")
    assert defer.calls == [
        ("ask", {"question": "What did RBI decide?", "answer_id": r.json()["answer_id"]})
    ]
    assert defer.commits_seen == [1]  # the row is committed before the job can run


def test_ask_passes_verified_only_on(fakes) -> None:
    client, _session, defer = fakes
    client.post("/v1/ask", headers=AUTH, json={"question": "q?", "verified_only": True})
    assert defer.calls[0][1]["verified_only"] is True


def test_ask_refuses_extra_fields(fakes) -> None:
    """The client cannot pick the chat or the answer row the job writes to."""
    client, session, defer = fakes
    for extra in ({"chat_id": 5}, {"answer_id": 1}, {"doc_id": 3}):
        body = {"question": "q?", **extra}
        assert client.post("/v1/ask", headers=AUTH, json=body).status_code == 422
    assert session.added == [] and defer.calls == []


def test_ask_that_cannot_be_queued_leaves_no_row(settings) -> None:
    app = create_app(settings)
    session, defer = FakeSession(), FakeDefer(fail=True)
    use_fakes(app, session, defer)
    r = TestClient(app).post("/v1/ask", headers=AUTH, json={"question": "q?"})
    assert r.status_code == 503 and r.json() == {"detail": "Service unavailable"}
    assert session.deleted == session.added and session.commits == 2


def test_answer_status_pending_has_no_answer() -> None:
    assert answer_status(_answer("pending")).model_dump() == {"status": "pending", "answer": None}


def test_answer_status_keeps_valid_citations_only() -> None:
    good = {"n": 1, "doc_path": "wiki/rbi.md", "title": "RBI", "heading": "Rates", "verified": True}
    row = _answer("answered", text="Held at 5.5% [C1].", citations=[good, {"n": "x"}, "junk"])
    status = answer_status(row)
    assert status.status == "answered"
    assert status.answer is not None and [c.doc_path for c in status.answer.citations] == [
        "wiki/rbi.md"
    ]


def test_unknown_status_is_shown_as_needing_review() -> None:
    assert answer_status(_answer("weird", text="x")).status == "needs_review"


def test_answer_routes(settings) -> None:
    app = create_app(settings)
    answered = _answer("answered", text="ok")
    saved = _answer("answered", text="ok", saved_path="wiki/answers/x.md")
    saved.id = 8
    pending = _answer("pending")
    pending.id = 9
    session = FakeSession(
        {(AnswerRow, 7): answered, (AnswerRow, 8): saved, (AnswerRow, 9): pending}
    )
    defer = FakeDefer()
    use_fakes(app, session, defer)
    c = TestClient(app)
    assert c.get("/v1/answers/7", headers=AUTH).json()["answer"]["text"] == "ok"
    assert c.get("/v1/answers/404", headers=AUTH).status_code == 404
    assert c.get("/v1/answers/0", headers=AUTH).status_code == 422
    assert c.get(f"/v1/answers/{2**63}", headers=AUTH).status_code == 422
    assert c.post("/v1/answers/9/save", headers=AUTH).status_code == 409
    assert c.post("/v1/answers/8/save", headers=AUTH).status_code == 202
    assert defer.calls == []  # already saved: not queued again
    assert c.post("/v1/answers/7/save", headers=AUTH).status_code == 202
    assert defer.calls == [("save_answer", {"answer_id": 7})]


# --- read-only GETs -----------------------------------------------------------------------


def _dependency_calls(dependant: object) -> set[object]:
    calls: set[object] = set()
    for d in getattr(dependant, "dependencies", []):
        calls.add(d.call)
        calls |= _dependency_calls(d)
    return calls


def test_get_routes_use_the_read_only_role_and_queue_nothing(client: TestClient) -> None:
    """GET never changes data (SEC-54): no GET can get a tr_app session or defer a job."""
    seen = 0
    for r in client.app.routes:
        contexts = getattr(r, "effective_route_contexts", None)
        for ctx in contexts() if callable(contexts) else []:
            if not ctx.path.startswith("/v1") or "GET" not in ctx.methods:
                continue
            calls = _dependency_calls(ctx.dependant)
            assert deps.get_session not in calls, ctx.path
            assert deps.get_defer not in calls, ctx.path
            seen += 1
    assert seen >= 8


# --- quiz, today ------------------------------------------------------------------------


def test_quiz_question_never_carries_a_key() -> None:
    q = quiz_question(3, "Which layer routes?", ["Transport", "Network", "Link", "Physical"])
    assert q is not None and set(q.model_dump()) == {"mcq_id", "question", "options"}
    assert quiz_question(3, "q", ["one"]) is None
    assert quiz_question(3, "q", ["a", "b", "c", "d", "e"]) is None
    assert quiz_question(3, "q", ["a", 2]) is None
    assert quiz_question(3, "q", {"a": 1}) is None


def test_quiz_answer_body_is_bounded(fakes) -> None:
    client, _session, _defer = fakes
    for chosen in (-1, 4, "1", 1.5, True):
        r = client.post("/v1/quiz/1/answer", headers=AUTH, json={"chosen": chosen})
        assert r.status_code == 422, chosen


def test_today_item_reads_both_shapes() -> None:
    plan_shape = {
        "cluster_id": 12,
        "title": "LangGraph 1.3 released",
        "section": "tech",
        "exam_tags": ["gate", 3],
        "verified_headline": True,
        "four_questions": {"why": "New API", "how_it_affects_me": "Upgrade"},
        "note_path": "radar/langgraph.md",
    }
    item = today_item(plan_shape)
    assert item is not None
    assert (item.cluster_id, item.four_questions.why, item.exam_tags) == ("12", "New API", ["gate"])
    flat = {"cluster_id": "c1", "title": "t", "section": "economy", "why": "w", "domains": ["x"]}
    item = today_item(flat)
    assert item is not None and item.four_questions.why == "w" and item.verified_headline is False
    assert today_item({"title": "t", "section": "not-a-section"}) is None
    assert today_item(["not", "a", "mapping"]) is None


# --- settings ---------------------------------------------------------------------------


def test_settings_validation(fakes) -> None:
    client, session, _defer = fakes
    bad = [
        {"briefing_time": "25:99", "sections": [], "verified_only_default": False},
        {"briefing_time": "07:00", "sections": ["tech", "evil"]},
        {"briefing_time": "07:00", "sections": ["tech"], "owner_login": "x"},
    ]
    for body in bad:
        assert client.put("/v1/settings", headers=AUTH, json=body).status_code == 422
    assert session.added == []


def test_merge_settings_ignores_a_bad_stored_value() -> None:
    defaults = default_settings()
    stored = {"briefing_time": "99:99", "sections": ["tech"], "verified_only_default": True}
    merged = merge_settings(stored, defaults)
    assert merged.briefing_time == defaults.briefing_time
    assert merged.sections == ["tech"] and merged.verified_only_default is True
    assert isinstance(merged, UserSettings)


# --- models -----------------------------------------------------------------------------


def test_models_status_shape(settings) -> None:
    app = create_app(settings)
    app.dependency_overrides[deps.get_roles] = lambda: {"worker": "qwen3.5:4b"}
    app.dependency_overrides[deps.get_loaded_models] = lambda: [
        {"name": "qwen3.5:4b", "size_bytes": 10, "size_vram_bytes": 8}
    ]
    app.dependency_overrides[deps.get_memory] = lambda: (16, 8)
    body = TestClient(app).get("/v1/models/status", headers=AUTH).json()
    assert "worker" in body["roles"]
    assert body["loaded"] == [{"name": "qwen3.5:4b", "size_bytes": 10, "size_vram_bytes": 8}]
    assert (body["ram_total_bytes"], body["ram_available_bytes"]) == (16, 8)


def test_roles_come_from_roles_yaml() -> None:
    roles = deps.get_roles()
    assert roles["worker"] and set(roles) == {"worker", "checker", "night", "embed", "vision"}


def test_parse_ollama_ps_skips_junk() -> None:
    payload = {
        "models": [
            {"name": "bge-m3", "size": 100, "size_vram": 90, "digest": "x"},
            {"name": "", "size": 1},
            {"name": "x", "size": -1},
            {"name": "y", "size": True},
            "junk",
        ]
    }
    assert parse_ollama_ps(payload) == [
        {"name": "bge-m3", "size_bytes": 100, "size_vram_bytes": 90}
    ]
    assert parse_ollama_ps(["not", "a", "dict"]) == []


async def test_ollama_ps_is_empty_when_ollama_is_away() -> None:
    assert await ollama_ps("http://127.0.0.1:9") == []
    assert await ollama_ps("file:///etc/passwd") == []


def test_parse_meminfo() -> None:
    text = "MemTotal:       16000 kB\nMemFree: 1 kB\nMemAvailable:    8000 kB\n"
    assert parse_meminfo(text) == (16000 * 1024, 8000 * 1024)
    assert parse_meminfo("garbage") == (0, 0)
