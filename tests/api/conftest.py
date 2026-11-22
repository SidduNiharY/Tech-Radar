"""Shared fixtures for the API tests.

The service token is a real secret file (mode 0600) in a temporary secrets folder, read by
the same code as in production: the API has no test-only way in.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from starlette.testclient import TestClient

from techradar.api.main import create_app
from techradar.settings import Settings

TOKEN = "t0ken-for-tests-0123456789abcdef"  # noqa: S105
OWNER = "owner@tailnet.test"
AUTH = {"X-Service-Token": TOKEN, "X-TR-User": OWNER}


def write_token(secrets_dir: Path, token: str = TOKEN) -> None:
    secrets_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    f = secrets_dir / "api_service_token"
    f.write_text(token + "\n", encoding="utf-8")
    f.chmod(0o600)


def api_settings(secrets_dir: Path, **kw: object) -> Settings:
    base: dict[str, object] = {
        "env": "dev",
        "telegram_owner_chat_id": 1,
        "owner_login": OWNER,
        "secrets_dir": secrets_dir,
    }
    base.update(kw)
    return Settings(**base)  # type: ignore[arg-type]


@pytest.fixture
def secrets_dir(tmp_path: Path) -> Path:
    d = tmp_path / "secrets"
    write_token(d)
    return d


@pytest.fixture
def settings(secrets_dir: Path) -> Settings:
    return api_settings(secrets_dir)


@pytest.fixture
def client(settings: Settings) -> TestClient:
    return TestClient(create_app(settings))


@pytest.fixture
def prod_client(secrets_dir: Path) -> TestClient:
    app = create_app(api_settings(secrets_dir, env="prod"))
    return TestClient(app, base_url="http://localhost")  # prod does not trust "testserver"
