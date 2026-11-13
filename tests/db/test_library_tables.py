"""Library tables (Phase 2c Task 1): models, migration chain and constraints."""

from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from techradar.db.engine import make_engine
from techradar.db.models import (
    Base,
    BookEval,
    Chunk,
    LibraryChapter,
    LibraryDoc,
    LibraryPart,
    StarterPack,
    StarterPackItem,
)
from techradar.settings import Settings

SHA_A = "a" * 64


def test_library_tables_registered_in_metadata():
    for name in (
        "library_docs",
        "library_parts",
        "library_chapters",
        "book_evals",
        "starter_packs",
        "starter_pack_items",
    ):
        assert f"techradar.{name}" in Base.metadata.tables


def test_library_models_columns():
    assert LibraryDoc.__table__.columns["sha256"].unique
    assert LibraryDoc.__table__.columns["sha256"].type.length == 64
    assert LibraryDoc.__table__.columns["title"].type.length == 300
    assert LibraryPart.__table__.columns["attempts"].server_default is not None
    assert LibraryChapter.__table__.columns["missing_pages"].server_default is not None
    assert BookEval.__table__.columns["question"].type.length == 300
    assert StarterPack.__table__.columns["name"].unique
    assert "pack_id" in StarterPackItem.__table__.columns


def test_chunk_new_columns():
    cols = Chunk.__table__.columns
    for name in ("doc_id", "chapter_id", "page", "ts_start", "context_label"):
        assert name in cols and cols[name].nullable
    index_names = {i.name for i in Chunk.__table__.indexes}
    assert "ix_chunks_doc_chapter_ordinal" in index_names


def test_enum_check_constraints_present():
    names = {c.name for c in LibraryDoc.__table__.constraints if c.name}
    assert {"ck_library_docs_kind", "ck_library_docs_status"} <= names


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


_INSERT_DOC = """
INSERT INTO techradar.library_docs
    (sha256, title, kind, origin, original_path, size_bytes, status, trust)
VALUES (:sha, 'Test book', 'pdf', 'library', 'x.pdf', 10, 'queued', 'open')
RETURNING id
"""


@pytest.mark.db
async def test_library_doc_sha_unique(app_conn):
    await app_conn.execute(
        text("DELETE FROM techradar.library_docs WHERE sha256 = :s"), {"s": SHA_A}
    )
    await app_conn.execute(text(_INSERT_DOC), {"sha": SHA_A})
    try:
        with pytest.raises(IntegrityError):
            await app_conn.execute(text(_INSERT_DOC), {"sha": SHA_A})
    finally:
        await app_conn.execute(
            text("DELETE FROM techradar.library_docs WHERE sha256 = :s"), {"s": SHA_A}
        )


@pytest.mark.db
async def test_library_doc_rejects_bad_kind(app_conn):
    with pytest.raises(IntegrityError):
        await app_conn.execute(
            text(
                """
                INSERT INTO techradar.library_docs
                    (sha256, title, kind, origin, original_path, size_bytes, status, trust)
                VALUES (:sha, 't', 'exe', 'library', 'x', 1, 'queued', 'open')
                """
            ),
            {"sha": "b" * 64},
        )


@pytest.mark.db
async def test_chunk_page_columns_exist(app_conn):
    await app_conn.execute(text("DELETE FROM techradar.chunks WHERE doc_path = 'lib-test'"))
    await app_conn.execute(
        text("DELETE FROM techradar.library_docs WHERE sha256 = :s"), {"s": "c" * 64}
    )
    doc_id = (await app_conn.execute(text(_INSERT_DOC), {"sha": "c" * 64})).scalar_one()
    try:
        await app_conn.execute(
            text(
                """
                INSERT INTO techradar.chunks (
                    doc_path, doc_kind, title, ordinal, text, lang, content_hash,
                    doc_id, chapter_id, page
                ) VALUES (
                    'lib-test', 'library', 'T', 0, 'hello', 'en', :h, :d, 7, 12
                )
                """
            ),
            {"h": "0" * 64, "d": doc_id},
        )
        page = (
            await app_conn.execute(
                text("SELECT page FROM techradar.chunks WHERE doc_id = :d"), {"d": doc_id}
            )
        ).scalar_one()
        assert page == 12
    finally:
        await app_conn.execute(
            text("DELETE FROM techradar.chunks WHERE doc_id = :d"), {"d": doc_id}
        )
        await app_conn.execute(
            text("DELETE FROM techradar.library_docs WHERE id = :d"), {"d": doc_id}
        )


@pytest.mark.db
async def test_library_part_defaults(app_conn):
    await app_conn.execute(
        text("DELETE FROM techradar.library_docs WHERE sha256 = :s"), {"s": "d" * 64}
    )
    doc_id = (await app_conn.execute(text(_INSERT_DOC), {"sha": "d" * 64})).scalar_one()
    try:
        row = (
            (
                await app_conn.execute(
                    text(
                        "INSERT INTO techradar.library_parts (doc_id, ordinal) VALUES (:d, 0) "
                        "RETURNING status, attempts"
                    ),
                    {"d": doc_id},
                )
            )
            .mappings()
            .one()
        )
        assert row["status"] == "pending"
        assert row["attempts"] == 0
    finally:
        await app_conn.execute(
            text("DELETE FROM techradar.library_parts WHERE doc_id = :d"), {"d": doc_id}
        )
        await app_conn.execute(
            text("DELETE FROM techradar.library_docs WHERE id = :d"), {"d": doc_id}
        )


@pytest.fixture
async def ro_conn(db_settings: Settings):
    engine = make_engine("ro", db_settings)
    async with engine.connect() as conn:
        await conn.execution_options(isolation_level="AUTOCOMMIT")
        yield conn
    await engine.dispose()


@pytest.mark.db
@pytest.mark.parametrize(
    "table",
    [
        "library_docs",
        "library_parts",
        "library_chapters",
        "book_evals",
        "starter_packs",
        "starter_pack_items",
    ],
)
async def test_read_only_role_cannot_write_library_tables(ro_conn, table):
    # The read-only role (Ask, the web UI) must never change the library.
    with pytest.raises(DBAPIError, match="permission denied"):
        await ro_conn.execute(text(f"DELETE FROM techradar.{table}"))  # noqa: S608


@pytest.mark.db
async def test_part_must_belong_to_an_existing_doc(app_conn):
    with pytest.raises(IntegrityError):
        await app_conn.execute(
            text("INSERT INTO techradar.library_parts (doc_id, ordinal) VALUES (-1, 0)")
        )


@pytest.mark.db
async def test_library_doc_rejects_bad_status_and_trust(app_conn):
    for status, trust in [("bogus", "open"), ("queued", "bogus")]:
        with pytest.raises(IntegrityError):
            await app_conn.execute(
                text(
                    """
                    INSERT INTO techradar.library_docs
                        (sha256, title, kind, origin, original_path, size_bytes, status, trust)
                    VALUES (:sha, 't', 'pdf', 'library', 'x', 1, :st, :tr)
                    """
                ),
                {"sha": "e" * 64, "st": status, "tr": trust},
            )
