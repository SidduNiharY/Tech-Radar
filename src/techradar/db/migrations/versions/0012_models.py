"""Models admin, model switch logs, evals, and trend counts

Revision ID: 0012_models
Revises: 0011_live_group
Create Date: 2026-11-15

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012_models"
down_revision: str | None = "0011_live_group"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "techradar"
NEW_TABLES = [
    "model_registry",
    "model_changes",
    "model_tests",
    "model_requests",
    "playground_runs",
    "trend_counts",
]


def upgrade() -> None:
    # 1. model_registry
    op.create_table(
        "model_registry",
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("ollama_tag", sa.Text(), nullable=False),
        sa.Column("family", sa.Text(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("role"),
        schema=SCHEMA,
    )

    # 2. model_changes
    op.create_table(
        "model_changes",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("old_tag", sa.Text(), nullable=False),
        sa.Column("new_tag", sa.Text(), nullable=False),
        # Families are kept so a rollback restores the family rule's input too.
        sa.Column("old_family", sa.Text(), nullable=True),
        sa.Column("new_family", sa.Text(), nullable=True),
        sa.Column("test_id", sa.BigInteger(), nullable=True),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "rolled_back",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )

    # 3. model_tests
    op.create_table(
        "model_tests",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("tag", sa.Text(), nullable=False),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column(
            "at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )

    # 4. model_requests
    op.create_table(
        "model_requests",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("tag", sa.Text(), nullable=False),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )

    # 5. playground_runs
    op.create_table(
        "playground_runs",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("output", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )

    # 6. trend_counts
    op.create_table(
        "trend_counts",
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("term", sa.Text(), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("day", "term"),
        schema=SCHEMA,
    )

    # Permissions: the same as the other phases (tr_app reads and writes, tr_ro reads).
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
