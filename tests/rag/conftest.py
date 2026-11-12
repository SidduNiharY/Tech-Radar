"""Database fixtures for the `db`-marked RAG tests (server only).

Each indexer test uses its own temporary vault but the same database, so a
note indexed by one test looks "removed" to the next. `rag_db` empties the
search-index tables around each test, only when TR_DB_TESTS_MAY_WIPE=1 (set by
`make test-db`); never run these tests against a database with real notes.
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
from sqlalchemy import text

from techradar.db.engine import make_engine
from techradar.settings import Settings

RAG_TABLES = ("chunks", "docs_index")


async def _wipe() -> None:
    settings = Settings(
        telegram_owner_chat_id=1,
        db_host="127.0.0.1",
        db_port=55432,
        db_name="techradar",
        secrets_dir=Path("secrets"),
    )
    engine = make_engine("migrator", settings)
    tables = ", ".join(f"techradar.{t}" for t in RAG_TABLES)
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    await engine.dispose()


@pytest.fixture
async def rag_db() -> AsyncGenerator[None]:
    if os.environ.get("TR_DB_TESTS_MAY_WIPE") != "1":
        pytest.skip("set TR_DB_TESTS_MAY_WIPE=1 (make test-db does) to allow wiping test tables")
    await _wipe()
    yield
    await _wipe()
