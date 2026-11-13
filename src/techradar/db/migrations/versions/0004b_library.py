"""Library tables and chunk columns for books and videos

Revision ID: 0004b_library
Revises: 0004_rag
Create Date: 2026-11-13

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004b_library"
down_revision: str | None = "0004_rag"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "techradar"
NEW_TABLES = [
    "library_docs",
    "library_parts",
    "library_chapters",
    "book_evals",
    "starter_packs",
    "starter_pack_items",
]


def _ts(name: str, nullable: bool = False, now: bool = True) -> sa.Column:
    return sa.Column(
        name,
        sa.DateTime(timezone=True),
        server_default=sa.text("now()") if now else None,
        nullable=nullable,
    )


def upgrade() -> None:
    op.create_table(
        "library_docs",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("origin", sa.Text(), nullable=False),
        sa.Column("original_path", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("pages", sa.Integer(), nullable=True),
        sa.Column("duration_s", sa.Float(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("trust", sa.Text(), nullable=False),
        sa.Column(
            "exam_tags",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("pack_item_id", sa.BigInteger(), nullable=True),
        sa.Column("keep_media", sa.Boolean(), server_default="false", nullable=False),
        _ts("created_at"),
        _ts("ready_at", nullable=True, now=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sha256"),
        sa.CheckConstraint(
            "kind IN ('pdf','docx','epub','video','audio','html')", name="ck_library_docs_kind"
        ),
        sa.CheckConstraint("origin IN ('library','pack')", name="ck_library_docs_origin"),
        sa.CheckConstraint(
            "status IN ('queued','processing','awaiting_transcription','ready',"
            "'quarantined','rejected','failed')",
            name="ck_library_docs_status",
        ),
        sa.CheckConstraint("trust IN ('official','open','my_own')", name="ck_library_docs_trust"),
        schema=SCHEMA,
    )

    op.create_table(
        "library_parts",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("doc_id", sa.BigInteger(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("page_start", sa.Integer(), nullable=True),
        sa.Column("page_end", sa.Integer(), nullable=True),
        sa.Column("ts_start", sa.Float(), nullable=True),
        sa.Column("ts_end", sa.Float(), nullable=True),
        sa.Column("status", sa.Text(), server_default="pending", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("job_id", sa.String(length=32), nullable=True),
        sa.Column("result_path", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["doc_id"], ["techradar.library_docs.id"]),
        sa.CheckConstraint("status IN ('pending','done','failed')", name="ck_library_parts_status"),
        schema=SCHEMA,
    )

    op.create_table(
        "library_chapters",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("doc_id", sa.BigInteger(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("page_start", sa.Integer(), nullable=True),
        sa.Column("page_end", sa.Integer(), nullable=True),
        sa.Column("ts_start", sa.Float(), nullable=True),
        sa.Column("ts_end", sa.Float(), nullable=True),
        sa.Column("text_path", sa.Text(), nullable=False),
        sa.Column("summary_path", sa.Text(), nullable=True),
        sa.Column(
            "missing_pages",
            postgresql.ARRAY(sa.Integer()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        _ts("read_at", nullable=True, now=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["doc_id"], ["techradar.library_docs.id"]),
        schema=SCHEMA,
    )

    op.create_table(
        "book_evals",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("doc_id", sa.BigInteger(), nullable=False),
        sa.Column("question", sa.String(length=300), nullable=False),
        sa.Column("expected_chunk_ids", postgresql.ARRAY(sa.BigInteger()), nullable=False),
        _ts("created_at"),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["doc_id"], ["techradar.library_docs.id"]),
        schema=SCHEMA,
    )

    op.create_table(
        "starter_packs",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("exam", sa.Text(), nullable=False),
        sa.Column("approved", sa.Boolean(), server_default="false", nullable=False),
        _ts("updated_at"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
        schema=SCHEMA,
    )

    op.create_table(
        "starter_pack_items",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("pack_id", sa.BigInteger(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("licence", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default="pending", nullable=False),
        sa.Column("doc_id", sa.BigInteger(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["pack_id"], ["techradar.starter_packs.id"]),
        sa.CheckConstraint(
            "status IN ('pending','downloaded','failed','rejected')",
            name="ck_starter_pack_items_status",
        ),
        schema=SCHEMA,
    )

    op.create_index(
        "ux_library_parts_doc_ordinal",
        "library_parts",
        ["doc_id", "ordinal"],
        unique=True,
        schema=SCHEMA,
    )
    op.create_index(
        "ux_library_chapters_doc_ordinal",
        "library_chapters",
        ["doc_id", "ordinal"],
        unique=True,
        schema=SCHEMA,
    )
    op.create_index("ix_book_evals_doc_id", "book_evals", ["doc_id"], schema=SCHEMA)

    op.add_column("chunks", sa.Column("doc_id", sa.BigInteger(), nullable=True), schema=SCHEMA)
    op.add_column("chunks", sa.Column("chapter_id", sa.BigInteger(), nullable=True), schema=SCHEMA)
    op.add_column("chunks", sa.Column("page", sa.Integer(), nullable=True), schema=SCHEMA)
    op.add_column("chunks", sa.Column("ts_start", sa.Float(), nullable=True), schema=SCHEMA)
    op.add_column("chunks", sa.Column("context_label", sa.Text(), nullable=True), schema=SCHEMA)
    op.create_index(
        "ix_chunks_doc_chapter_ordinal",
        "chunks",
        ["doc_id", "chapter_id", "ordinal"],
        unique=False,
        schema=SCHEMA,
    )

    # Same privileges 0004_rag grants for its tables.
    stmts = ["DO $$ BEGIN", "IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'tr_app') THEN"]
    stmts += [
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON techradar.{t} TO tr_app;" for t in NEW_TABLES
    ]
    stmts += [
        "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA techradar TO tr_app;",
        "END IF;",
        "IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'tr_ro') THEN",
    ]
    stmts += [f"GRANT SELECT ON techradar.{t} TO tr_ro;" for t in NEW_TABLES]
    stmts += ["END IF;", "END $$;"]
    op.execute("\n".join(stmts))


def downgrade() -> None:
    op.drop_index("ix_chunks_doc_chapter_ordinal", table_name="chunks", schema=SCHEMA)
    for col in ("context_label", "ts_start", "page", "chapter_id", "doc_id"):
        op.drop_column("chunks", col, schema=SCHEMA)
    for table in reversed(NEW_TABLES):
        op.drop_table(table, schema=SCHEMA)
