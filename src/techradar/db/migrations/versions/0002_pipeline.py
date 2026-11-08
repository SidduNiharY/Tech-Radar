"""pipeline tables

Revision ID: 0002_pipeline
Revises: 0001_baseline
Create Date: 2026-11-08

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0002_pipeline"
down_revision: str | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Enable pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    # sources table
    op.create_table(
        "sources",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("kind", sa.Text(), server_default="rss", nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("host", sa.Text(), nullable=False),
        sa.Column("section", sa.Text(), nullable=False),
        sa.Column("trust_tier", sa.Text(), nullable=False),
        sa.Column("interval_min", sa.Integer(), server_default="120", nullable=False),
        sa.Column("etag", sa.Text(), nullable=True),
        sa.Column("last_modified", sa.Text(), nullable=True),
        sa.Column("last_fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("enabled", sa.Boolean(), server_default="false", nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
        sa.UniqueConstraint("url"),
        schema="techradar",
    )

    # fetch_runs table
    op.create_table(
        "fetch_runs",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("source_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("new_items", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error", sa.String(length=500), nullable=True),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["techradar.sources.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="techradar",
    )

    # raw_items table
    op.create_table(
        "raw_items",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("source_id", sa.BigInteger(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("url_hash", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raw_name", sa.Text(), nullable=True),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default="new", nullable=False),
        sa.Column("reject_reason", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["techradar.sources.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("url_hash"),
        schema="techradar",
    )
    op.create_index(
        "ix_raw_items_status",
        "raw_items",
        ["status"],
        unique=False,
        schema="techradar",
    )

    # items table
    op.create_table(
        "items",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("raw_item_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("domain", sa.Text(), nullable=False),
        sa.Column("lang", sa.Text(), nullable=False),
        sa.Column("text_path", sa.Text(), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("embedding", Vector(1024), nullable=True),
        sa.Column("cluster_id", sa.BigInteger(), nullable=True),
        sa.Column("relevance", sa.Float(), nullable=True),
        sa.Column("status", sa.Text(), server_default="new", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("section", sa.Text(), nullable=True),
        sa.Column(
            "exam_tags",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column(
            "flags",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("reader_json", postgresql.JSONB(), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["raw_item_id"],
            ["techradar.raw_items.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("raw_item_id"),
        schema="techradar",
    )
    op.create_index(
        "ix_items_status",
        "items",
        ["status"],
        unique=False,
        schema="techradar",
    )
    op.create_index(
        "ix_items_cluster_id",
        "items",
        ["cluster_id"],
        unique=False,
        schema="techradar",
    )
    op.create_index(
        "ix_items_embedding_hnsw",
        "items",
        ["embedding"],
        unique=False,
        schema="techradar",
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )

    # facts table
    op.create_table(
        "facts",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("fact_key", sa.Text(), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("value", sa.Text(), nullable=True),
        sa.Column("section", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default="unverified", nullable=False),
        sa.Column("source_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("subject_key", sa.Text(), nullable=True),
        sa.Column("as_of", sa.Date(), nullable=True),
        sa.Column("superseded_by", sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(
            ["superseded_by"],
            ["techradar.facts.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("fact_key"),
        schema="techradar",
    )

    # fact_changes table
    op.create_table(
        "fact_changes",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("subject_key", sa.Text(), nullable=False),
        sa.Column("old_fact_id", sa.BigInteger(), nullable=False),
        sa.Column("new_fact_id", sa.BigInteger(), nullable=False),
        sa.Column("old_value", sa.Text(), nullable=True),
        sa.Column("new_value", sa.Text(), nullable=True),
        sa.Column(
            "at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["old_fact_id"],
            ["techradar.facts.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["new_fact_id"],
            ["techradar.facts.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="techradar",
    )

    # intake_log table
    op.create_table(
        "intake_log",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("job_id", sa.String(length=32), nullable=False),
        sa.Column("origin", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("mime", sa.Text(), nullable=False),
        sa.Column("verdict", sa.Text(), nullable=False),
        sa.Column("steps", postgresql.JSONB(), nullable=False),
        sa.Column(
            "reasons",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column(
            "at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="techradar",
    )

    # quarantine_items table
    op.create_table(
        "quarantine_items",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("job_id", sa.String(length=32), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("origin", sa.Text(), nullable=False),
        sa.Column(
            "reasons",
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
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now() + interval '7 days'"),
            nullable=False,
        ),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id"),
        schema="techradar",
    )

    # fact_sources table
    op.create_table(
        "fact_sources",
        sa.Column("fact_id", sa.BigInteger(), nullable=False),
        sa.Column("item_id", sa.BigInteger(), nullable=False),
        sa.Column("domain", sa.Text(), nullable=False),
        sa.Column("quote", sa.String(length=300), nullable=True),
        sa.Column("supported", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["fact_id"],
            ["techradar.facts.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["item_id"],
            ["techradar.items.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("fact_id", "item_id"),
        schema="techradar",
    )

    # notes table
    op.create_table(
        "notes",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("vault_path", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("cluster_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "source_domains",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column(
            "source_urls",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "written_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("vault_path"),
        sa.UniqueConstraint("cluster_id"),
        schema="techradar",
    )


def downgrade() -> None:
    op.drop_table("notes", schema="techradar")
    op.drop_table("fact_sources", schema="techradar")
    op.drop_table("quarantine_items", schema="techradar")
    op.drop_table("intake_log", schema="techradar")
    op.drop_table("fact_changes", schema="techradar")
    op.drop_table("facts", schema="techradar")
    op.drop_index("ix_items_embedding_hnsw", table_name="items", schema="techradar")
    op.drop_index("ix_items_cluster_id", table_name="items", schema="techradar")
    op.drop_index("ix_items_status", table_name="items", schema="techradar")
    op.drop_table("items", schema="techradar")
    op.drop_index("ix_raw_items_status", table_name="raw_items", schema="techradar")
    op.drop_table("raw_items", schema="techradar")
    op.drop_table("fetch_runs", schema="techradar")
    op.drop_table("sources", schema="techradar")
