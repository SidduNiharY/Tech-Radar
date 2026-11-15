"""Practice, briefing, flashcards, MCQs and exam watch tables

Revision ID: 0005_practice
Revises: 0004b_library
Create Date: 2026-11-15

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_practice"
down_revision: str | None = "0004b_library"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "techradar"
NEW_TABLES = [
    "briefings",
    "takes",
    "mcqs",
    "quiz_attempts",
    "flashcards",
    "mistakes",
    "vocab",
    "grammar_items",
    "exam_watches",
    "alerts",
    "review_decisions",
]


def upgrade() -> None:
    # 1. briefings
    op.create_table(
        "briefings",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("date", name="uq_briefings_date"),
        schema=SCHEMA,
    )

    # 2. takes
    op.create_table(
        "takes",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("briefing_id", sa.BigInteger(), nullable=False),
        sa.Column("text", sa.String(length=500), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["briefing_id"],
            [f"{SCHEMA}.briefings.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )

    # 3. mcqs
    op.create_table(
        "mcqs",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("fact_id", sa.BigInteger(), nullable=True),
        sa.Column("chunk_id", sa.BigInteger(), nullable=True),
        sa.Column("chapter_id", sa.BigInteger(), nullable=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("options", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("answer_index", sa.Integer(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("status", sa.Text(), server_default="active", nullable=False),
        sa.ForeignKeyConstraint(["fact_id"], [f"{SCHEMA}.facts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["chunk_id"], [f"{SCHEMA}.chunks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["chapter_id"],
            [f"{SCHEMA}.library_chapters.id"],
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "(fact_id IS NOT NULL AND chunk_id IS NULL) "
            "OR (fact_id IS NULL AND chunk_id IS NOT NULL)",
            name="ck_mcqs_single_source",
        ),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )

    # 4. quiz_attempts
    op.create_table(
        "quiz_attempts",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("mcq_id", sa.BigInteger(), nullable=False),
        sa.Column("chosen_index", sa.Integer(), nullable=False),
        sa.Column("correct", sa.Boolean(), nullable=False),
        sa.Column(
            "answered_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("date", sa.Date(), nullable=False),
        sa.ForeignKeyConstraint(["mcq_id"], [f"{SCHEMA}.mcqs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )

    # 5. flashcards
    op.create_table(
        "flashcards",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("front", sa.Text(), nullable=False),
        sa.Column("back", sa.Text(), nullable=False),
        sa.Column("source_kind", sa.Text(), nullable=False),
        sa.Column("source_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "fsrs_card",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("due", sa.DateTime(timezone=True), nullable=False),
        sa.Column("first_shown_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("chunk_id", sa.BigInteger(), nullable=True),
        sa.Column("doc_path", sa.Text(), nullable=True),
        sa.Column("page", sa.Integer(), nullable=True),
        sa.Column("ts_start", sa.Integer(), nullable=True),
        sa.Column("retired", sa.Boolean(), server_default="false", nullable=False),
        sa.ForeignKeyConstraint(["chunk_id"], [f"{SCHEMA}.chunks.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )

    # 6. mistakes
    op.create_table(
        "mistakes",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("ref_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "detail",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )

    # 7. vocab
    op.create_table(
        "vocab",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("word", sa.Text(), nullable=False),
        sa.Column("sentence", sa.Text(), nullable=False),
        sa.Column("meaning", sa.Text(), nullable=False),
        sa.Column(
            "synonyms",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "antonyms",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("word", name="uq_vocab_word"),
        schema=SCHEMA,
    )

    # 8. grammar_items
    op.create_table(
        "grammar_items",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("options", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("answer_index", sa.Integer(), nullable=False),
        sa.Column("rule", sa.Text(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )

    # 9. exam_watches
    op.create_table(
        "exam_watches",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("watch_uuid", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("url", name="uq_exam_watches_url"),
        schema=SCHEMA,
    )

    # 10. alerts
    op.create_table(
        "alerts",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("watch_id", sa.BigInteger(), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["watch_id"], [f"{SCHEMA}.exam_watches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )

    # 11. review_decisions
    op.create_table(
        "review_decisions",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("item_id", sa.BigInteger(), nullable=False),
        sa.Column("decision", sa.Text(), nullable=False),
        sa.Column(
            "decided_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )

    # Seed row: sources.id = 0, name 'manual'
    op.execute(
        sa.text(
            "INSERT INTO techradar.sources "
            "(id, name, kind, url, host, section, trust_tier, enabled) "
            "VALUES (0, 'manual', 'manual', 'manual://inbox', 'manual', 'inbox', 'manual', true) "
            "ON CONFLICT (id) DO NOTHING;"
        )
    )

    # Permissions
    stmts = ["DO $$ BEGIN", "IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'tr_app') THEN"]
    stmts += [
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON {SCHEMA}.{t} TO tr_app;" for t in NEW_TABLES
    ]
    stmts += [
        f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA {SCHEMA} TO tr_app;",
        "END IF;",
        "IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'tr_ro') THEN",
    ]
    stmts += [f"GRANT SELECT ON {SCHEMA}.{t} TO tr_ro;" for t in NEW_TABLES]
    stmts += ["END IF;", "END $$;"]
    op.execute("\n".join(stmts))


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM techradar.sources WHERE id = 0;"))
    for table in reversed(NEW_TABLES):
        op.drop_table(table, schema=SCHEMA)
