"""The API must fail closed when it is not configured (SEC-27, SEC-41, SEC-51).

Before: with no api_service_token secret, the expected token fell back to
$TR_API_SERVICE_TOKEN and then to the literal "test-token"; production still
trusted the test-only Host "testserver"; the built-in owner placeholder was
accepted; and /v1/ask took empty or unbounded questions.
"""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from techradar.api.deps import set_test_credentials
from techradar.api.main import create_app
from techradar.settings import Settings

OWNER = "siddu@tailnet.test"


@pytest.fixture(autouse=True)
def _no_test_credentials() -> Generator[None]:
    set_test_credentials(None, None)
    yield
    set_test_credentials(None, None)


def settings(tmp_path: Path, **kw: object) -> Settings:
    base: dict[str, object] = {
        "env": "prod",
        "telegram_owner_chat_id": 1,
        "owner_login": OWNER,
        "secrets_dir": tmp_path / "secrets",
    }
    base.update(kw)
    return Settings(**base)  # type: ignore[arg-type]


def write_token(tmp_path: Path, token: str) -> None:
    d = tmp_path / "secrets"
    d.mkdir(mode=0o700, exist_ok=True)
    f = d / "api_service_token"
    f.write_text(token, encoding="utf-8")
    f.chmod(0o600)


def client(s: Settings) -> TestClient:
    return TestClient(create_app(s), base_url="http://localhost")


def test_no_secret_means_no_access_even_with_test_token(tmp_path: Path):
    r = client(settings(tmp_path)).get(
        "/v1/ping", headers={"X-Service-Token": "test-token", "X-TR-User": OWNER}
    )
    assert r.status_code == 503


def test_environment_variable_is_not_a_token_source(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("TR_API_SERVICE_TOKEN", "from-env")
    r = client(settings(tmp_path)).get(
        "/v1/ping", headers={"X-Service-Token": "from-env", "X-TR-User": OWNER}
    )
    assert r.status_code == 503


def test_token_from_secret_file_is_accepted(tmp_path: Path):
    write_token(tmp_path, "s3cret-token")
    r = client(settings(tmp_path)).get(
        "/v1/ping", headers={"X-Service-Token": "s3cret-token", "X-TR-User": OWNER}
    )
    assert r.status_code == 200


def test_prod_refuses_the_test_only_host(tmp_path: Path):
    write_token(tmp_path, "s3cret-token")
    r = TestClient(create_app(settings(tmp_path))).get("/healthz")  # Host: testserver
    assert r.status_code == 400


def test_prod_refuses_the_placeholder_owner_login(tmp_path: Path):
    write_token(tmp_path, "s3cret-token")
    s = settings(tmp_path, owner_login="owner@local")
    r = client(s).get(
        "/v1/ping", headers={"X-Service-Token": "s3cret-token", "X-TR-User": "owner@local"}
    )
    assert r.status_code == 503


@pytest.mark.parametrize("question", ["", "x" * 501])
def test_ask_rejects_empty_or_too_long_questions(tmp_path: Path, question: str):
    write_token(tmp_path, "s3cret-token")
    r = client(settings(tmp_path)).post(
        "/v1/ask",
        json={"question": question},
        headers={"X-Service-Token": "s3cret-token", "X-TR-User": OWNER},
    )
    assert r.status_code == 422


def test_ask_accepts_a_normal_question(tmp_path: Path):
    write_token(tmp_path, "s3cret-token")
    r = client(settings(tmp_path)).post(
        "/v1/ask",
        json={"question": "What is the repo rate?"},
        headers={"X-Service-Token": "s3cret-token", "X-TR-User": OWNER},
    )
    assert r.status_code == 200
