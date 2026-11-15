"""Feedback signals, action log, weights, preference rules, profiles, and reports

Revision ID: 0013_feedback
Revises: 0012_models
Create Date: 2026-11-15

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0013_feedback"
down_revision: str | None = "0012_models"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "techradar"
NEW_TABLES = [
    "feedback",
    "action_log",
    "edits",
    "weights",
    "preference_rules",
    "regression_cases",
    "improvement_log",
    "style_profiles",
    "topic_mastery",
    "liked_examples",
    "preference_pairs",
    "improvement_reports",
]


def upgrade() -> None:
    # 1. feedback
    op.create_table(
        "feedback",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("target_kind", sa.Text(), nullable=False),
        sa.Column("target_id", sa.BigInteger(), nullable=False),
        sa.Column("signal", sa.Text(), nullable=False),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column(
            "at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "target_kind",
            "target_id",
            "signal",
            "day",
            name="uq_feedback_target_signal_day",
        ),
        schema=SCHEMA,
    )

    # 2. action_log
    op.create_table(
        "action_log",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("target", sa.String(length=200), nullable=False),
        sa.Column("topic", sa.Text(), nullable=True),
        sa.Column("source", sa.Text(), nullable=True),
        sa.Column("mode", sa.Text(), nullable=True),
        sa.Column(
            "at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )

    # 3. edits
    op.create_table(
        "edits",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("doc_path", sa.Text(), nullable=False),
        sa.Column("before_hash", sa.String(length=64), nullable=False),
        sa.Column("after_hash", sa.String(length=64), nullable=False),
        sa.Column("length_change", sa.Integer(), nullable=False),
        sa.Column(
            "sections_removed",
            postgresql.ARRAY(sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("words_replaced", sa.Integer(), nullable=False),
        sa.Column(
            "at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )

    # 4. weights
    op.create_table(
        "weights",
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("floor", sa.Float(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("kind", "key"),
        schema=SCHEMA,
    )

    # 5. preference_rules
    op.create_table(
        "preference_rules",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("mode", sa.Text(), nullable=True),
        sa.Column("field", sa.Text(), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column(
            "proposed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("report_id", sa.BigInteger(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )

    # 6. regression_cases
    op.create_table(
        "regression_cases",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("question", sa.String(length=500), nullable=False),
        sa.Column("doc_id", sa.BigInteger(), nullable=True),
        sa.Column("bad_answer", sa.Text(), nullable=False),
        sa.Column("must_not_include", sa.String(length=300), nullable=False),
        sa.Column("must_include", sa.String(length=300), nullable=True),
        sa.Column("from_feedback_id", sa.BigInteger(), nullable=True),
        sa.Column("passing", sa.Boolean(), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )

    # 7. improvement_log
    op.create_table(
        "improvement_log",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("before", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("after", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("automatic", sa.Boolean(), nullable=False),
        sa.Column(
            "at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("undone_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )

    # 8. style_profiles
    op.create_table(
        "style_profiles",
        sa.Column("mode", sa.Text(), nullable=False),
        sa.Column("setup", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("mode"),
        schema=SCHEMA,
    )

    # 9. topic_mastery
    op.create_table(
        "topic_mastery",
        sa.Column("topic", sa.Text(), nullable=False),
        sa.Column("level", sa.Text(), nullable=False),
        sa.Column("quiz_accuracy", sa.Float(), nullable=True),
        sa.Column("stability_days", sa.Float(), nullable=True),
        sa.Column("reviews", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("prev_level", sa.Text(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("topic"),
        schema=SCHEMA,
    )

    # 10. liked_examples
    op.create_table(
        "liked_examples",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("mode", sa.Text(), nullable=False),
        sa.Column("question", sa.String(length=500), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(1024), nullable=True),
        sa.Column("from_feedback_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "fact_ids",
            postgresql.ARRAY(sa.BigInteger()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )

    # 11. preference_pairs
    op.create_table(
        "preference_pairs",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("mode", sa.Text(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("version_a", sa.Text(), nullable=False),
        sa.Column("version_b", sa.Text(), nullable=False),
        sa.Column("variant_a", sa.Text(), nullable=False),
        sa.Column("variant_b", sa.Text(), nullable=False),
        sa.Column("chosen", sa.Text(), nullable=True),
        sa.Column(
            "asked_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )

    # 12. improvement_reports
    op.create_table(
        "improvement_reports",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("week_start"),
        schema=SCHEMA,
    )


def downgrade() -> None:
    for table in reversed(NEW_TABLES):
        op.drop_table(table, schema=SCHEMA)
