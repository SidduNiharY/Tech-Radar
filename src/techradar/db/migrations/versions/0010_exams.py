"""Exams: syllabus, PYQs, drills, mock results, cutoffs, topic weights, and sources

Revision ID: 0010_exams
Revises: 0009_world
Create Date: 2026-11-15

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010_exams"
down_revision: str | None = "0009_world"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "techradar"
NEW_TABLES = [
    "syllabus_topics",
    "pyq_questions",
    "drill_attempts",
    "mock_results",
    "cutoffs",
    "topic_weights",
    "topic_sources",
]


def upgrade() -> None:
    # 1. syllabus_topics
    op.create_table(
        "syllabus_topics",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("exam", sa.Text(), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("topic", sa.Text(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("vault_path", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "exam",
            "subject",
            "slug",
            name="uq_syllabus_topics_exam_subject_slug",
        ),
        schema=SCHEMA,
    )

    # 2. pyq_questions
    op.create_table(
        "pyq_questions",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("exam", sa.Text(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("paper", sa.Text(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("options", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("qtype", sa.Text(), nullable=False),
        sa.Column("answer_key", sa.Text(), nullable=False),
        sa.Column("marks", sa.Numeric(precision=4, scale=2), nullable=False),
        sa.Column("topic_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "tag_status",
            sa.Text(),
            server_default=sa.text("'none'"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["topic_id"],
            [f"{SCHEMA}.syllabus_topics.id"],
            name="fk_pyq_questions_topic_id",
        ),
        sa.CheckConstraint("qtype IN ('MCQ','MSQ','NAT')", name="ck_pyq_questions_qtype"),
        sa.CheckConstraint(
            "tag_status IN ('none','suggested','confirmed')",
            name="ck_pyq_questions_tag_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )

    # 3. drill_attempts
    op.create_table(
        "drill_attempts",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("item", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("chosen", sa.Text(), nullable=False),
        sa.Column("correct", sa.Boolean(), nullable=False),
        sa.Column("seconds", sa.Float(), nullable=False),
        sa.Column(
            "at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )

    # 4. mock_results
    op.create_table(
        "mock_results",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("exam", sa.Text(), nullable=False),
        sa.Column("taken_on", sa.Date(), nullable=False),
        sa.Column("total", sa.Float(), nullable=False),
        sa.Column("max_total", sa.Float(), nullable=True),
        sa.Column("sections", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )

    # 5. cutoffs
    op.create_table(
        "cutoffs",
        sa.Column("exam", sa.Text(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("tier", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("exam", "year", "tier", "category"),
        schema=SCHEMA,
    )

    # 6. topic_weights
    op.create_table(
        "topic_weights",
        sa.Column("exam", sa.Text(), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("topic", sa.Text(), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("exam", "subject", "topic"),
        schema=SCHEMA,
    )

    # 7. topic_sources
    op.create_table(
        "topic_sources",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("topic_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("ref_id", sa.BigInteger(), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["topic_id"],
            [f"{SCHEMA}.syllabus_topics.id"],
            name="fk_topic_sources_topic_id",
        ),
        sa.CheckConstraint(
            "kind IN ('chapter','pyq','pack_item','note')", name="ck_topic_sources_kind"
        ),
        sa.CheckConstraint(
            "status IN ('suggested','confirmed','dismissed')", name="ck_topic_sources_status"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "topic_id",
            "kind",
            "ref_id",
            name="uq_topic_sources_topic_kind_ref",
        ),
        schema=SCHEMA,
    )

    # 8. exam_watches capture columns
    op.add_column(
        "exam_watches",
        sa.Column("capture_pattern", sa.Text(), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        "exam_watches",
        sa.Column("capture_exam", sa.Text(), nullable=True),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_column("exam_watches", "capture_exam", schema=SCHEMA)
    op.drop_column("exam_watches", "capture_pattern", schema=SCHEMA)
    for table in reversed(NEW_TABLES):
        op.drop_table(table, schema=SCHEMA)
