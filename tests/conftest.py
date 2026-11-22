"""Shared fixtures for `db`-marked tests (phases 3 to 12).

They need the Postgres from `compose.dev.yaml` (127.0.0.1:55432, migrations
applied) and the role passwords in ./secrets, so they run on the server only
(`make test-db`). A test module may define its own `session` fixture; the
nearest one wins.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from techradar.db.engine import make_engine
from techradar.settings import Settings

TEST_OWNER_CHAT_ID = 4242  # a fake id; tests never touch the real owner


@pytest.fixture
def db_settings() -> Settings:
    return Settings(
        telegram_owner_chat_id=TEST_OWNER_CHAT_ID,
        db_host="127.0.0.1",
        db_port=55432,
        db_name="techradar",
        secrets_dir=Path("secrets"),
    )


@pytest.fixture
async def session(db_settings: Settings) -> AsyncGenerator[AsyncSession]:
    """A session as the app role; every change is rolled back after the test."""
    engine = make_engine("app", db_settings)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s
        await s.rollback()
    await engine.dispose()
