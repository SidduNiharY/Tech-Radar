"""Database helpers for the `db`-marked API tests (server only).

They need the Postgres from `compose.dev.yaml` (127.0.0.1:55432, migrations applied) and
the role passwords in ./secrets. The routes commit, so the tables they touch are emptied
before and after each test, and only when TR_DB_TESTS_MAY_WIPE=1 (set by `make test-db`).

Engines use NullPool: the TestClient runs the app in its own event loop, so no connection
may outlive the loop that opened it.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from starlette.testclient import TestClient

from techradar.api import deps
from techradar.api.main import create_app
from techradar.db.engine import DbRole, database_url
from techradar.settings import Settings
from tests.api.conftest import NOW, FakeDefer

API_TABLES = (
    "answers",
    "user_settings",
    "takes",
    "briefings",
    "plans",
    "quiz_attempts",
    "mistakes",
    "mcqs",
    "flashcards",
    "pending_actions",
)
CHUNK_PREFIX = "tests-api/"


def db_settings() -> Settings:
    return Settings(
        telegram_owner_chat_id=1,
        db_host="127.0.0.1",
        db_port=55432,
        db_name="techradar",
        secrets_dir=Path("secrets"),
    )


def factory(role: DbRole) -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(database_url(role, db_settings()), poolclass=NullPool)
    return async_sessionmaker(engine, expire_on_commit=False)


def run_db[T](fn: Callable[[AsyncSession], Awaitable[T]], role: DbRole = "app") -> T:
    """Run `fn` in a fresh session (committed afterwards) outside the app's loop."""

    async def go() -> T:
        async with factory(role)() as session:
            result = await fn(session)
            await session.commit()
            return result

    return asyncio.run(go())


def wipe() -> None:
    async def go() -> None:
        async with factory("migrator")() as session:
            tables = ", ".join(f"techradar.{t}" for t in API_TABLES)
            await session.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
            await session.execute(
                text("DELETE FROM techradar.chunks WHERE doc_path LIKE :p"),
                {"p": f"{CHUNK_PREFIX}%"},
            )
            await session.commit()

    asyncio.run(go())


def may_wipe() -> None:
    if os.environ.get("TR_DB_TESTS_MAY_WIPE") != "1":
        pytest.skip("set TR_DB_TESTS_MAY_WIPE=1 (make test-db does) to allow wiping test tables")


def db_client(settings: Settings, defer: FakeDefer, now: Any = NOW) -> TestClient:
    """The real app with real `tr_app` / `tr_ro` sessions and a recording job queue."""
    app = create_app(settings)

    def dep(role: DbRole) -> Callable[[], AsyncIterator[AsyncSession]]:
        f = factory(role)

        async def session() -> AsyncIterator[AsyncSession]:
            async with f() as s:
                yield s

        return session

    app.dependency_overrides[deps.get_session] = dep("app")
    app.dependency_overrides[deps.get_ro_session] = dep("ro")
    app.dependency_overrides[deps.get_defer] = lambda: defer
    app.dependency_overrides[deps.get_now] = lambda: now
    return TestClient(app)
