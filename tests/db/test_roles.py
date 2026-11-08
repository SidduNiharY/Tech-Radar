"""Integration tests for database role privileges and constraints."""

from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from techradar.db.engine import make_engine
from techradar.settings import Settings

pytestmark = pytest.mark.db


@pytest.fixture
def db_settings() -> Settings:
    return Settings(
        telegram_owner_chat_id=1,
        db_host="127.0.0.1",
        db_port=55432,
        db_name="techradar",
        secrets_dir=Path("secrets"),
    )


@pytest.fixture
async def app_conn(db_settings: Settings):
    engine = make_engine("app", db_settings)
    async with engine.connect() as conn:
        await conn.execution_options(isolation_level="AUTOCOMMIT")
        yield conn
    await engine.dispose()


@pytest.fixture
async def ro_conn(db_settings: Settings):
    engine = make_engine("ro", db_settings)
    async with engine.connect() as conn:
        await conn.execution_options(isolation_level="AUTOCOMMIT")
        yield conn
    await engine.dispose()


async def test_app_can_insert_audit_event(app_conn):
    await app_conn.execute(
        text("INSERT INTO audit_log(actor, action, detail) VALUES ('test','ping','{}')")
    )


async def test_ro_cannot_insert(ro_conn):
    with pytest.raises(DBAPIError, match="permission denied"):
        await ro_conn.execute(
            text("INSERT INTO audit_log(actor, action, detail) VALUES ('t','x','{}')")
        )


async def test_app_cannot_create_table(app_conn):
    with pytest.raises(DBAPIError, match="permission denied"):
        await app_conn.execute(text("CREATE TABLE evil(id int)"))


async def test_app_cannot_drop_table(app_conn):
    with pytest.raises(DBAPIError, match="must be owner"):
        await app_conn.execute(text("DROP TABLE audit_log"))


async def test_vector_extension_installed(ro_conn):
    result = await ro_conn.execute(text("SELECT 1 FROM pg_extension WHERE extname='vector'"))
    assert result.scalar() == 1
