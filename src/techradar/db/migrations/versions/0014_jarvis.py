"""Jarvis sessions, turns, voice writes, greetings, and GPU lease

Revision ID: 0014_jarvis
Revises: 0013_feedback
Create Date: 2026-11-15

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014_jarvis"
down_revision: str | None = "0013_feedback"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "techradar"
NEW_TABLES = [
    "jarvis_sessions",
    "jarvis_turns",
    "jarvis_writes",
    "jarvis_greetings",
    "gpu_lease",
]


def upgrade() -> None:
    # 1. jarvis_sessions
    op.create_table(
        "jarvis_sessions",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("device", sa.Text(), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("practice", sa.Text(), nullable=True),
        sa.Column("quiz", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.CheckConstraint("device IN ('mac','phone','server')", name="ck_jarvis_sessions_device"),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )

    # 2. jarvis_turns
    op.create_table(
        "jarvis_turns",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("session_id", sa.BigInteger(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("text", sa.String(length=2000), nullable=False),
        sa.Column("skill", sa.Text(), nullable=True),
        sa.Column("list_len", sa.Integer(), nullable=True),
        sa.Column("ticket_id", sa.BigInteger(), nullable=True),
        sa.Column("reply_to", sa.BigInteger(), nullable=True),
        sa.Column("reply", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "keep",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("role IN ('me','jarvis')", name="ck_jarvis_turns_role"),
        sa.ForeignKeyConstraint(
            ["session_id"],
            [f"{SCHEMA}.jarvis_sessions.id"],
            name="fk_jarvis_turns_session_id",
        ),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )

    # 3. jarvis_writes
    op.create_table(
        "jarvis_writes",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("ticket_id", sa.BigInteger(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("args", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("inverse_action", sa.Text(), nullable=True),
        sa.Column(
            "inverse_args",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("tap_by", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("undone_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('awaiting_tap','done','expired','undone')",
            name="ck_jarvis_writes_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )

    # 4. jarvis_greetings
    op.create_table(
        "jarvis_greetings",
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("greeting", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "shown_devices",
            postgresql.ARRAY(sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("date"),
        schema=SCHEMA,
    )

    # 5. gpu_lease
    op.create_table(
        "gpu_lease",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("holder", sa.Text(), nullable=True),
        sa.Column("session_id", sa.BigInteger(), nullable=True),
        sa.Column("since", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("id = 1", name="ck_gpu_lease_single_row"),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )
    # The lease is one row that is updated, never inserted (Task 5): start it free.
    op.execute("INSERT INTO techradar.gpu_lease (id) VALUES (1)")


def downgrade() -> None:
    for table in reversed(NEW_TABLES):
        op.drop_table(table, schema=SCHEMA)
