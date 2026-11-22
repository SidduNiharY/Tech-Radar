"""Understanding and World: deep dives, glossary, timelines,
predictions, economy series, and fact checks

Revision ID: 0009_world
Revises: 0008_voice
Create Date: 2026-11-15

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009_world"
down_revision: str | None = "0008_voice"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "techradar"
NEW_TABLES = [
    "deep_dives",
    "glossary_terms",
    "timelines",
    "predictions",
    "econ_series",
    "fact_checks",
]


def upgrade() -> None:
    # 1. deep_dives
    op.create_table(
        "deep_dives",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("week", sa.Text(), nullable=False),
        sa.Column("topic", sa.Text(), nullable=False),
        sa.Column("vault_path", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )

    # 2. glossary_terms
    op.create_table(
        "glossary_terms",
        sa.Column("term", sa.Text(), nullable=False),
        sa.Column("vault_path", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("term"),
        schema=SCHEMA,
    )

    # 3. timelines
    op.create_table(
        "timelines",
        sa.Column("entity", sa.Text(), nullable=False),
        sa.Column("vault_path", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("entity"),
        schema=SCHEMA,
    )

    # 4. predictions
    op.create_table(
        "predictions",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("text", sa.String(length=280), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("outcome", sa.Integer(), nullable=True),
        sa.Column("outcome_text", sa.Text(), nullable=True),
        # Set when the reminder is sent, so each prediction is reminded once.
        sa.Column("reminded_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "outcome IS NULL OR outcome BETWEEN 1 AND 3", name="ck_predictions_outcome"
        ),
        schema=SCHEMA,
    )

    # 5. econ_series
    op.create_table(
        "econ_series",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("series", sa.Text(), nullable=False),
        sa.Column("period", sa.Date(), nullable=False),
        sa.Column("value", sa.Numeric(precision=12, scale=4), nullable=False),
        sa.Column("unit", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("source_kind", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "series",
            "period",
            "source_kind",
            name="uq_econ_series_period_source",
        ),
        schema=SCHEMA,
    )

    # 6. fact_checks
    op.create_table(
        "fact_checks",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("claims", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("verdicts", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("saved_path", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
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
