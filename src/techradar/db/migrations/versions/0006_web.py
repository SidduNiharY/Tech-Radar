"""Web app settings, pending action tickets, and briefing items

Revision ID: 0006_web
Revises: 0005_practice
Create Date: 2026-11-15

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_web"
down_revision: str | None = "0005_practice"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "techradar"
NEW_TABLES = [
    "user_settings",
    "pending_actions",
]


def upgrade() -> None:
    # 1. user_settings
    op.create_table(
        "user_settings",
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("key"),
        schema=SCHEMA,
    )

    # 2. pending_actions
    op.create_table(
        "pending_actions",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("token", sa.String(length=32), nullable=False),
        sa.Column("session_id", sa.Text(), nullable=False),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("args", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("args_hash", sa.String(length=64), nullable=False),
        sa.Column("summary", sa.String(length=300), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token", name="uq_pending_actions_token"),
        schema=SCHEMA,
    )

    # 3. Add column items to briefings
    op.add_column(
        "briefings",
        sa.Column(
            "items",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=True,
        ),
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
    op.drop_column("briefings", "items", schema=SCHEMA)
    for table in reversed(NEW_TABLES):
        op.drop_table(table, schema=SCHEMA)
