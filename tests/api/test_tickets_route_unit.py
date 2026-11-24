"""`POST /v1/tickets/confirm` without a database (Phase 4 Task 2b). SEC-56."""

from __future__ import annotations

from typing import Any

from starlette.testclient import TestClient

from techradar.api.main import create_app
from techradar.api.routes import tickets as route
from tests.api.conftest import AUTH, FakeDefer, FakeSession, use_fakes

TAB = "tab0123456789abcdef"
TOKEN = "a" * 32


def _client(settings, monkeypatch) -> tuple[TestClient, list[tuple[Any, ...]], FakeSession]:
    app = create_app(settings)
    session = FakeSession()
    use_fakes(app, session, FakeDefer())
    calls: list[tuple[Any, ...]] = []

    async def fake_run(s: Any, token: str, session_id: str, now: Any) -> tuple[str, str | None]:
        calls.append((token, session_id))
        return "ok", "Released."

    monkeypatch.setattr(route, "run_confirmed", fake_run)
    return TestClient(app), calls, session


def test_confirm_runs_the_ticket_in_the_tab_session(settings, monkeypatch) -> None:
    c, calls, session = _client(settings, monkeypatch)
    r = c.post("/v1/tickets/confirm", headers={**AUTH, "X-TR-Session": TAB}, json={"token": TOKEN})
    assert r.json() == {"result": "ok", "message": "Released."}
    assert calls == [(TOKEN, f"web:{TAB}")] and session.commits == 1


def test_confirm_needs_a_well_formed_tab_session(settings, monkeypatch) -> None:
    c, calls, _ = _client(settings, monkeypatch)
    for header in ({}, {"X-TR-Session": "short"}, {"X-TR-Session": "tg:1234567890123456"}):
        r = c.post("/v1/tickets/confirm", headers={**AUTH, **header}, json={"token": TOKEN})
        assert r.status_code == 400, header
    assert calls == []


def test_confirm_takes_only_a_token(settings, monkeypatch) -> None:
    """The client cannot say which action or arguments to run."""
    c, calls, _ = _client(settings, monkeypatch)
    headers = {**AUTH, "X-TR-Session": TAB}
    bodies: list[dict[str, Any]] = [
        {"token": "A" * 32},
        {"token": TOKEN[:-1]},
        {"token": TOKEN, "action": "quarantine.delete"},
        {"token": TOKEN, "args": {"id": 1}},
        {},
    ]
    for body in bodies:
        assert c.post("/v1/tickets/confirm", headers=headers, json=body).status_code == 422, body
    assert calls == []


def test_confirm_needs_the_caller_check_first(settings, monkeypatch) -> None:
    c, calls, _ = _client(settings, monkeypatch)
    r = c.post("/v1/tickets/confirm", headers={"X-TR-Session": TAB}, json={"token": TOKEN})
    assert r.status_code == 401 and calls == []
