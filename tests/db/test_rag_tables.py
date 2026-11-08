"""Tests for RAG tables, models and permissions (Phase 2b Task 2 / SEC-12, SEC-40)."""

from pathlib import Path

import pytest
from sqlalchemy import BigInteger, DateTime, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.exc import DBAPIError

from techradar.db.engine import make_engine
from techradar.db.models import Answer, Base, Chunk, DocsIndex, Outbox
from techradar.settings import Settings


def test_rag_tables_registered_in_metadata():
    expected_tables = {
        "techradar.chunks",
        "techradar.docs_index",
        "techradar.answers",
        "techradar.outbox",
    }
    for table_name in expected_tables:
        assert table_name in Base.metadata.tables, f"Table {table_name} missing from Base.metadata"


def test_chunk_model_columns():
    cols = Chunk.__table__.columns
    assert isinstance(cols["id"].type, BigInteger)
    assert cols["id"].primary_key
    assert isinstance(cols["doc_path"].type, Text)
    assert isinstance(cols["doc_kind"].type, Text)
    assert isinstance(cols["heading_path"].type, ARRAY)
    assert isinstance(cols["ordinal"].type, Integer)
    assert isinstance(cols["text"].type, Text)
    assert isinstance(cols["lang"].type, Text)
    assert isinstance(cols["exam_tags"].type, ARRAY)
    assert isinstance(cols["content_hash"].type, String)
    assert cols["content_hash"].type.length == 64
    assert isinstance(cols["indexed_at"].type, DateTime)


def test_docs_index_model_columns():
    cols = DocsIndex.__table__.columns
    assert isinstance(cols["doc_path"].type, Text)
    assert cols["doc_path"].primary_key
    assert isinstance(cols["content_hash"].type, String)
    assert isinstance(cols["indexed_at"].type, DateTime)


def test_answer_model_columns():
    cols = Answer.__table__.columns
    assert isinstance(cols["id"].type, BigInteger)
    assert cols["id"].primary_key
    assert isinstance(cols["chat_id"].type, BigInteger)
    assert isinstance(cols["question"].type, String)
    assert cols["question"].type.length == 500
    assert isinstance(cols["text"].type, Text)
    assert isinstance(cols["citations"].type, JSONB)
    assert isinstance(cols["flags"].type, ARRAY)


def test_outbox_model_columns():
    cols = Outbox.__table__.columns
    assert isinstance(cols["id"].type, BigInteger)
    assert cols["id"].primary_key
    assert isinstance(cols["chat_id"].type, BigInteger)
    assert isinstance(cols["kind"].type, Text)
    assert isinstance(cols["purpose"].type, Text)
    assert isinstance(cols["text"].type, String)
    assert cols["text"].type.length == 4096
    assert isinstance(cols["attempts"].type, Integer)


# DB integration fixtures and tests
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


@pytest.mark.db
async def test_chunk_tsv_is_generated(app_conn):
    # insert a chunk with text "Article 370 was discussed"
    # SELECT tsv @@ to_tsquery('simple','370') -> true
    await app_conn.execute(
        text(
            """
            INSERT INTO techradar.chunks (
                doc_path, doc_kind, title, heading_path, ordinal, text, lang,
                content_hash, indexed_at
            ) VALUES (
                'test.md', 'news', 'Article 370 Test', ARRAY['Polity'], 0,
                'Article 370 was discussed in the parliament.', 'en',
                '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef', now()
            )
            """
        )
    )
    result = await app_conn.execute(
        text(
            "SELECT tsv @@ to_tsquery('simple', '370') FROM techradar.chunks "
            "WHERE doc_path = 'test.md'"
        )
    )
    match = result.scalar_one()
    assert match is True
    await app_conn.execute(text("DELETE FROM techradar.chunks WHERE doc_path = 'test.md'"))


@pytest.mark.db
async def test_ro_cannot_write_chunks(ro_conn):
    with pytest.raises(DBAPIError, match="permission denied"):
        await ro_conn.execute(text("DELETE FROM techradar.chunks"))


@pytest.mark.db
async def test_outbox_row_defaults(app_conn):
    result = await app_conn.execute(
        text(
            """
            INSERT INTO techradar.outbox (chat_id, kind, purpose, text)
            VALUES (12345, 'text', 'answer', 'Sample answer text')
            RETURNING sent_at, attempts
            """
        )
    )
    row = result.mappings().one()
    assert row["sent_at"] is None
    assert row["attempts"] == 0
    await app_conn.execute(text("DELETE FROM techradar.outbox WHERE chat_id = 12345"))
