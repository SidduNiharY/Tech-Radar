"""RAG tables: chunks, docs_index, answers, outbox

Revision ID: 0004_rag
Revises: 0003_procrastinate
Create Date: 2026-11-08

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0004_rag"
down_revision: str | None = "0003_procrastinate"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # chunks table
    op.create_table(
        "chunks",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("doc_path", sa.Text(), nullable=False),
        sa.Column("doc_kind", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column(
            "heading_path",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("lang", sa.Text(), nullable=False),
        sa.Column("section", sa.Text(), nullable=True),
        sa.Column(
            "exam_tags",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("verified", sa.Boolean(), nullable=True),
        sa.Column("generated", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("flagged", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "source_domains",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("embedding", Vector(1024), nullable=True),
        sa.Column(
            "tsv",
            postgresql.TSVECTOR(),
            sa.Computed("to_tsvector('simple', text)", persisted=True),
            nullable=True,
        ),
        sa.Column(
            "indexed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="techradar",
    )

    op.create_index(
        "ix_chunks_embedding_hnsw",
        "chunks",
        ["embedding"],
        unique=False,
        schema="techradar",
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.create_index(
        "ix_chunks_tsv_gin",
        "chunks",
        ["tsv"],
        unique=False,
        schema="techradar",
        postgresql_using="gin",
    )
    op.create_index(
        "ix_chunks_doc_path",
        "chunks",
        ["doc_path"],
        unique=False,
        schema="techradar",
    )

    # docs_index table
    op.create_table(
        "docs_index",
        sa.Column("doc_path", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "indexed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("doc_path"),
        schema="techradar",
    )

    # answers table
    op.create_table(
        "answers",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("question", sa.String(length=500), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column(
            "citations",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("used_unverified", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "flags",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("saved_path", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        schema="techradar",
    )

    # outbox table
    op.create_table(
        "outbox",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("text", sa.String(length=4096), nullable=False),
        sa.Column("buttons", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("file_path", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_message_id", sa.BigInteger(), nullable=True),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("ref_id", sa.BigInteger(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        schema="techradar",
    )

    # Grant permissions to tr_app and tr_ro
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'tr_app') THEN
                GRANT SELECT, INSERT, UPDATE, DELETE ON techradar.chunks TO tr_app;
                GRANT SELECT, INSERT, UPDATE, DELETE ON techradar.docs_index TO tr_app;
                GRANT SELECT, INSERT, UPDATE, DELETE ON techradar.answers TO tr_app;
                GRANT SELECT, INSERT, UPDATE, DELETE ON techradar.outbox TO tr_app;
                GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA techradar TO tr_app;
            END IF;
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'tr_ro') THEN
                GRANT SELECT ON techradar.chunks TO tr_ro;
                GRANT SELECT ON techradar.docs_index TO tr_ro;
                GRANT SELECT ON techradar.answers TO tr_ro;
                GRANT SELECT ON techradar.outbox TO tr_ro;
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.drop_table("outbox", schema="techradar")
    op.drop_table("answers", schema="techradar")
    op.drop_table("docs_index", schema="techradar")
    op.drop_index("ix_chunks_doc_path", table_name="chunks", schema="techradar")
    op.drop_index("ix_chunks_tsv_gin", table_name="chunks", schema="techradar")
    op.drop_index("ix_chunks_embedding_hnsw", table_name="chunks", schema="techradar")
    op.drop_table("chunks", schema="techradar")
