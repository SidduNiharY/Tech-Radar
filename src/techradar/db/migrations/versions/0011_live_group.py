"""Study group mode and live voice session tracking

Revision ID: 0011_live_group
Revises: 0010_exams
Create Date: 2026-11-15

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_live_group"
down_revision: str | None = "0010_exams"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "techradar"
NEW_TABLES = [
    "group_members",
    "group_polls",
    "group_answers",
    "live_sessions",
]


def upgrade() -> None:
    # 1. group_members
    op.create_table(
        "group_members",
        sa.Column("member_hash", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=32), nullable=False),
        sa.PrimaryKeyConstraint("member_hash"),
        schema=SCHEMA,
    )

    # 2. group_polls
    op.create_table(
        "group_polls",
        sa.Column("poll_id", sa.Text(), nullable=False),
        sa.Column("mcq_id", sa.BigInteger(), nullable=False),
        sa.Column("group_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "sent_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("poll_id"),
        schema=SCHEMA,
    )

    # 3. group_answers
    op.create_table(
        "group_answers",
        sa.Column("poll_id", sa.Text(), nullable=False),
        sa.Column("member_hash", sa.String(length=64), nullable=False),
        sa.Column("correct", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("poll_id", "member_hash"),
        schema=SCHEMA,
    )

    # 4. live_sessions
    op.create_table(
        "live_sessions",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("mode", sa.Text(), nullable=False),
        sa.Column("dir", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("status", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )


def downgrade() -> None:
    for table in reversed(NEW_TABLES):
        op.drop_table(table, schema=SCHEMA)
