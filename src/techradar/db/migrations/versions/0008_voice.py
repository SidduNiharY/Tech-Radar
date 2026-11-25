"""Voice Coach, sessions, metrics, pronunciation, writing and stories

Revision ID: 0008_voice
Revises: 0007_planner
Create Date: 2026-11-15

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_voice"
down_revision: str | None = "0007_planner"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "techradar"
NEW_TABLES = [
    "voice_sessions",
    "voice_metrics",
    "pronunciation_scores",
    "writing_feedback",
    "stories",
    "story_drafts",
    "listening",
    "reflections",
    "voice_notices",
]


def upgrade() -> None:
    # 1. voice_sessions
    op.create_table(
        "voice_sessions",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("duration_s", sa.Float(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("audio_path", sa.Text(), nullable=True),
        sa.Column(
            "kept",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("delete_after", sa.DateTime(timezone=True), nullable=True),
        sa.Column("peaks", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("transcript", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )

    # 2. voice_metrics
    op.create_table(
        "voice_metrics",
        sa.Column("session_id", sa.BigInteger(), nullable=False),
        sa.Column("words_per_min", sa.Float(), nullable=False),
        sa.Column("filler_count", sa.Integer(), nullable=False),
        sa.Column("fillers_per_min", sa.Float(), nullable=False),
        sa.Column("filler_breakdown", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("long_pauses", sa.Integer(), nullable=False),
        sa.Column("avg_sentence_words", sa.Float(), nullable=False),
        sa.Column("type_token_ratio", sa.Float(), nullable=False),
        sa.Column("overused", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"],
            [f"{SCHEMA}.voice_sessions.id"],
            name="fk_voice_metrics_session_id",
        ),
        sa.PrimaryKeyConstraint("session_id"),
        schema=SCHEMA,
    )

    # 3. pronunciation_scores
    op.create_table(
        "pronunciation_scores",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("session_id", sa.BigInteger(), nullable=False),
        sa.Column("word", sa.Text(), nullable=False),
        sa.Column("start_s", sa.Float(), nullable=False),
        sa.Column("end_s", sa.Float(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("flagged", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"],
            [f"{SCHEMA}.voice_sessions.id"],
            name="fk_pronunciation_scores_session_id",
        ),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )

    # 4. writing_feedback
    op.create_table(
        "writing_feedback",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("source_kind", sa.Text(), nullable=False),
        sa.Column("source_id", sa.BigInteger(), nullable=True),
        sa.Column("original_text", sa.Text(), nullable=False),
        sa.Column("critique", sa.Text(), nullable=False),
        sa.Column("polished_text", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )

    # 5. stories
    op.create_table(
        "stories",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )

    # 6. story_drafts
    op.create_table(
        "story_drafts",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("story_id", sa.BigInteger(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("feedback", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["story_id"],
            [f"{SCHEMA}.stories.id"],
            name="fk_story_drafts_story_id",
        ),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )

    # 7. listening
    op.create_table(
        "listening",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("audio_path", sa.Text(), nullable=False),
        sa.Column("transcript", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )

    # 8. reflections
    op.create_table(
        "reflections",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )

    # 9. voice_notices
    op.create_table(
        "voice_notices",
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "sent_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("chat_id"),
        schema=SCHEMA,
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
    for table in reversed(NEW_TABLES):
        op.drop_table(table, schema=SCHEMA)
