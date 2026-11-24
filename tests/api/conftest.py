"""Shared fixtures for the API tests.

The service token is a real secret file (mode 0600) in a temporary secrets folder, read by
the same code as in production: the API has no test-only way in.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

from techradar.api import deps
from techradar.api.main import create_app
from techradar.settings import Settings

TOKEN = "t0ken-for-tests-0123456789abcdef"  # noqa: S105
OWNER = "owner@tailnet.test"
AUTH = {"X-Service-Token": TOKEN, "X-TR-User": OWNER}
NOW = datetime(2026, 11, 22, 9, 0, tzinfo=UTC)


class FakeSession:
    """Enough of AsyncSession for routes that add, get, delete and commit."""

    def __init__(self, rows: dict[tuple[type, int], object] | None = None) -> None:
        self.rows = dict(rows or {})
        self.added: list[Any] = []
        self.deleted: list[Any] = []
        self.commits = 0
        self._next_id = 100

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                self._next_id += 1
                obj.id = self._next_id

    async def commit(self) -> None:
        await self.flush()
        self.commits += 1

    async def delete(self, obj: Any) -> None:
        self.deleted.append(obj)

    async def get(self, model: type, key: int) -> object | None:
        return self.rows.get((model, key))


class FakeDefer:
    """Records deferred jobs as (task name, kwargs); can be made to fail."""

    def __init__(self, fail: bool = False) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.fail = fail
        self.session: FakeSession | None = None
        self.commits_seen: list[int] = []

    async def __call__(self, name: str, args: Any) -> None:
        if self.session is not None:
            self.commits_seen.append(self.session.commits)
        if self.fail:
            raise ConnectionError("queue down")
        self.calls.append((name, dict(args)))


def use_fakes(app: Any, session: FakeSession, defer: FakeDefer, now: datetime = NOW) -> None:
    """Point the route dependencies at the fakes (no database, no queue)."""

    async def fake_session() -> Any:
        return session

    def fake_defer() -> FakeDefer:
        return defer

    defer.session = session
    app.dependency_overrides[deps.get_session] = fake_session
    app.dependency_overrides[deps.get_ro_session] = fake_session
    app.dependency_overrides[deps.get_defer] = fake_defer
    app.dependency_overrides[deps.get_now] = lambda: now


def app_routes(app: object) -> list[tuple[str, set[str]]]:
    """(path, methods) of every HTTP route, including those of included routers.

    FastAPI 0.162 keeps an included router as one `_IncludedRouter` entry in `app.routes`,
    with no `path`: a plain loop over `app.routes` sees none of the `/v1` routes.
    """
    out: list[tuple[str, set[str]]] = []
    for r in getattr(app, "routes", []):
        contexts = getattr(r, "effective_route_contexts", None)
        entries = list(contexts()) if callable(contexts) else [r]
        for e in entries:
            path, methods = getattr(e, "path", ""), getattr(e, "methods", None)
            if path and methods:
                out.append((path, set(methods)))
    return out


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
