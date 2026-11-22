"""Tests for API service authentication and security middleware (SEC-27, SEC-41, SEC-51)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from fastapi import Depends
from starlette.testclient import TestClient

from techradar.api import deps
from techradar.api.main import MAX_BODY, create_app
from tests.api.conftest import AUTH, OWNER, TOKEN, api_settings, write_token


def test_missing_or_wrong_token_401(client: TestClient) -> None:
    assert client.get("/v1/ping").status_code == 401
    assert (
        client.get("/v1/ping", headers={"X-Service-Token": "bad", "X-TR-User": OWNER}).status_code
        == 401
    )
    assert client.get("/v1/ping", headers={"X-TR-User": OWNER}).status_code == 401


def test_wrong_user_403(client: TestClient) -> None:
    assert (
        client.get(
            "/v1/ping", headers={"X-Service-Token": TOKEN, "X-TR-User": "someone@else"}
        ).status_code
        == 403
    )
    assert client.get("/v1/ping", headers={"X-Service-Token": TOKEN}).status_code == 403


def test_ok_with_both(client: TestClient) -> None:
    resp = client.get("/v1/ping", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json() == {"pong": True}


def test_docs_hidden_in_prod(prod_client: TestClient) -> None:
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert prod_client.get(path).status_code == 404, path


def test_body_too_large_413(client: TestClient) -> None:
    assert client.post("/v1/ping", headers=AUTH, content=b"x" * 70_000).status_code == 413


def test_foreign_host_rejected(client: TestClient) -> None:
    assert client.get("/healthz", headers={"Host": "evil.example"}).status_code == 400


def test_every_v1_route_requires_auth(client: TestClient) -> None:
    for r in client.app.routes:
        if getattr(r, "path", "").startswith("/v1"):
            for m in r.methods - {"HEAD", "OPTIONS"}:
                path = r.path.replace("{", "").replace("}", "")
                assert client.request(m, path).status_code in (401, 422), r.path


def test_healthz_unauthenticated(client: TestClient) -> None:
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_status_endpoint(client: TestClient) -> None:
    resp = client.get("/v1/status", headers=AUTH)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["version"] == "0.1.0"


def test_token_is_read_from_the_secret_file(tmp_path: Path) -> None:
    write_token(tmp_path / "s", "file-secret-token")
    c = TestClient(create_app(api_settings(tmp_path / "s")))
    ok = {"X-Service-Token": "file-secret-token", "X-TR-User": OWNER}
    assert c.get("/v1/ping", headers=ok).json() == {"pong": True}
    assert c.get("/v1/ping", headers={**ok, "X-Service-Token": "wrong-token"}).status_code == 401


# --- added 2026-11-22 (Phase 4 Task 1 review) ------------------------------------------


def test_there_is_no_test_only_way_in() -> None:
    """Before: deps.set_test_credentials let any code replace the token and the owner."""
    assert not hasattr(deps, "set_test_credentials")
    assert not hasattr(deps, "_test_service_token")


def test_non_ascii_credentials_give_401_and_403_not_500(client: TestClient) -> None:
    """compare_digest raises TypeError on non-ASCII str; that was a 500."""
    bad_token = {"X-Service-Token": "tök€n".encode(), "X-TR-User": OWNER.encode()}
    assert client.get("/v1/ping", headers=bad_token).status_code == 401
    bad_user = {"X-Service-Token": TOKEN.encode(), "X-TR-User": "öwner".encode()}
    assert client.get("/v1/ping", headers=bad_user).status_code == 403


def test_owner_must_match_exactly(client: TestClient) -> None:
    for user in (OWNER.upper(), f" {OWNER}", f"{OWNER}x", OWNER[:-1]):
        assert client.get("/v1/ping", headers={**AUTH, "X-TR-User": user}).status_code == 403


def test_chunked_body_over_the_limit_is_413(client: TestClient) -> None:
    def chunks() -> Iterator[bytes]:
        for _ in range(MAX_BODY // 1024 + 2):
            yield b"x" * 1024

    assert client.post("/v1/ping", headers=AUTH, content=chunks()).status_code == 413


def test_chunked_body_under_the_limit_reaches_the_route(client: TestClient) -> None:
    def chunks() -> Iterator[bytes]:
        yield b"{}"

    assert client.post("/v1/ping", headers=AUTH, content=chunks()).json() == {"pong": True}


def test_bad_content_length_is_400(client: TestClient) -> None:
    for value in ("abc", "-1", "1_000", "+5"):
        r = client.post("/v1/ping", headers={**AUTH, "Content-Length": value}, content=b"")
        assert r.status_code == 400, value


def test_body_limit_holds_before_auth(client: TestClient) -> None:
    """An unauthenticated caller cannot make the API buffer a large body either."""
    assert client.post("/v1/ping", content=b"x" * 70_000).status_code == 413


def test_auth_runs_before_any_route_dependency(settings) -> None:
    """An unauthenticated request never opens a database session or reaches the route."""
    app = create_app(settings)
    opened: list[str] = []

    def fake_session() -> str:
        opened.append("session")
        return "session"

    from fastapi import APIRouter

    router = APIRouter(prefix="/v1", dependencies=[Depends(deps.require_caller)])

    @router.get("/probe")
    def probe(s: str = Depends(fake_session)) -> dict[str, str]:
        return {"s": s}

    app.include_router(router)
    c = TestClient(app)
    assert c.get("/v1/probe").status_code == 401
    assert c.get("/v1/probe", headers={"X-Service-Token": TOKEN}).status_code == 403
    assert opened == []
    assert c.get("/v1/probe", headers=AUTH).json() == {"s": "session"}


def test_refusals_say_nothing_about_the_setup(tmp_path: Path) -> None:
    """A caller learns only the status: not that the secret is missing or the owner unset."""
    c = TestClient(create_app(api_settings(tmp_path / "none")))
    r = c.get("/v1/ping", headers=AUTH)
    assert r.status_code == 503
    assert r.json() == {"detail": "Service unavailable"}
    write_token(tmp_path / "s")
    c = TestClient(create_app(api_settings(tmp_path / "s")))
    assert c.get("/v1/ping").json() == {"detail": "Unauthorized"}
    assert c.get("/v1/ping", headers={**AUTH, "X-TR-User": "x"}).json() == {"detail": "Forbidden"}


def test_unhandled_errors_leak_nothing(settings) -> None:
    app = create_app(settings)

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("password=hunter2 at /run/secrets/tr_app_password")

    r = TestClient(app, raise_server_exceptions=False).get("/boom")
    assert r.status_code == 500
    assert r.json() == {"detail": "Internal error"}
    assert "hunter2" not in r.text and "secrets" not in r.text


def test_validation_errors_do_not_echo_the_input(settings) -> None:
    from pydantic import BaseModel, Field

    app = create_app(settings)

    class Body(BaseModel):
        q: str = Field(max_length=5)

    @app.post("/echo")
    def echo(b: Body) -> dict[str, str]:
        return {"q": b.q}

    r = TestClient(app).post("/echo", json={"q": "secret-input-value"})
    assert r.status_code == 422
    assert "secret-input-value" not in r.text
    [err] = r.json()["detail"]
    assert set(err) == {"loc", "msg", "type"}


def test_module_app_is_built_on_first_use() -> None:
    """`uvicorn techradar.api.main:app` (Task 6) finds an app; importing main builds none."""
    import techradar.api.main as main

    assert "app" not in vars(main)
    assert main.app.title == "TechRadar Brain API"
    assert main.app is main.app
