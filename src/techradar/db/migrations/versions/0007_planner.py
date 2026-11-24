"""Planner, study sessions, revisions, checkins and plans

Revision ID: 0007_planner
Revises: 0006_web
Create Date: 2026-11-15

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_planner"
down_revision: str | None = "0006_web"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "techradar"
NEW_TABLES = [
    "study_sessions",
    "revisions",
    "checkins",
    "plans",
    "job_alerts",
]


def upgrade() -> None:
    # 1. study_sessions
    op.create_table(
        "study_sessions",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("goal", sa.Text(), nullable=False),
        sa.Column("topic", sa.String(length=120), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("minutes", sa.Integer(), nullable=True),
        sa.Column(
            "auto_closed",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )

    # 2. revisions
    op.create_table(
        "revisions",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("goal", sa.Text(), nullable=False),
        sa.Column("topic", sa.Text(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("done_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("session_id", sa.BigInteger(), nullable=True),
        sa.Column("chapter_id", sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(
            ["session_id"],
            [f"{SCHEMA}.study_sessions.id"],
            name="fk_revisions_session_id",
        ),
        sa.ForeignKeyConstraint(
            ["chapter_id"],
            [f"{SCHEMA}.library_chapters.id"],
            name="fk_revisions_chapter_id",
        ),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )

    # 3. checkins
    op.create_table(
        "checkins",
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("sleep_band", sa.Integer(), nullable=True),
        sa.Column("energy", sa.Integer(), nullable=True),
        sa.Column("mood", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("date"),
        schema=SCHEMA,
    )

    # 4. plans
    op.create_table(
        "plans",
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column(
            "lines",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("date"),
        schema=SCHEMA,
    )

    # 5. job_alerts (Task 6): one row per alert key, for the 6-hour de-duplication.
    # Named job_alerts because `alerts` already belongs to the exam watcher.
    op.create_table(
        "job_alerts",
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("last_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("key"),
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
