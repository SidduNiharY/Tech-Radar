"""Tests for API service authentication and security middleware (SEC-27, SEC-41)."""

from collections.abc import Generator
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from techradar.api.deps import set_test_credentials
from techradar.api.main import create_app
from techradar.settings import Settings

TOKEN: str = "test-token"  # noqa: S105
OWNER: str = "owner@local"
AUTH: dict[str, str] = {
    "X-Service-Token": TOKEN,
    "X-TR-User": OWNER,
}


@pytest.fixture(autouse=True)
def _setup_credentials() -> Generator[None]:
    set_test_credentials(token=TOKEN, owner=OWNER)
    yield
    set_test_credentials(None, None)


@pytest.fixture
def client() -> TestClient:
    app = create_app(Settings(env="dev", telegram_owner_chat_id=1, owner_login=OWNER))
    return TestClient(app)


@pytest.fixture
def prod_client() -> TestClient:
    app = create_app(Settings(env="prod", telegram_owner_chat_id=1, owner_login=OWNER))
    return TestClient(app)


def test_missing_or_wrong_token_401(client: TestClient) -> None:
    assert client.get("/v1/ping").status_code == 401
    assert (
        client.get(
            "/v1/ping",
            headers={"X-Service-Token": "bad", "X-TR-User": OWNER},
        ).status_code
        == 401
    )
    assert client.get("/v1/ping", headers={"X-TR-User": OWNER}).status_code == 401


def test_wrong_user_403(client: TestClient) -> None:
    assert (
        client.get(
            "/v1/ping",
            headers={"X-Service-Token": TOKEN, "X-TR-User": "someone@else"},
        ).status_code
        == 403
    )
    assert client.get("/v1/ping", headers={"X-Service-Token": TOKEN}).status_code == 403


def test_ok_with_both(client: TestClient) -> None:
    resp = client.get("/v1/ping", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json() == {"pong": True}


def test_docs_hidden_in_prod(prod_client: TestClient) -> None:
    assert (
        prod_client.get("/docs").status_code == 404
        and prod_client.get("/openapi.json").status_code == 404
    )


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


def test_ask_endpoint(client: TestClient) -> None:
    resp = client.post("/v1/ask", headers=AUTH, json={"question": "What is Python?"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "queued"


def test_secret_file_auth(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    set_test_credentials(None, None)
    secret_file = tmp_path / "api_service_token"
    secret_file.write_text("file-secret-token\n")
    secret_file.chmod(0o600)

    s = Settings(
        env="dev",
        telegram_owner_chat_id=1,
        owner_login=OWNER,
        secrets_dir=tmp_path,
    )
    app = create_app(s)
    c = TestClient(app)

    # Calling with the file token works
    resp = c.get(
        "/v1/ping",
        headers={"X-Service-Token": "file-secret-token", "X-TR-User": OWNER},
    )
    assert resp.status_code == 200
    assert resp.json() == {"pong": True}

    # Calling with invalid token fails
    assert (
        c.get(
            "/v1/ping",
            headers={"X-Service-Token": "wrong-token", "X-TR-User": OWNER},
        ).status_code
        == 401
    )
