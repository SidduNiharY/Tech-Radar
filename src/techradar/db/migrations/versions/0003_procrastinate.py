"""procrastinate schema

Revision ID: 0003_procrastinate
Revises: 0002_pipeline
Create Date: 2026-11-08

"""

from collections.abc import Sequence

from alembic import op
from procrastinate.schema import SchemaManager

revision: str = "0003_procrastinate"
down_revision: str | None = "0002_pipeline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    schema_sql = SchemaManager.get_schema()
    op.execute(schema_sql)


def downgrade() -> None:
    # Drop procrastinate tables if downgraded
    op.execute(
        """
        DROP TABLE IF EXISTS procrastinate_periodic_def CASCADE;
        DROP TABLE IF EXISTS procrastinate_events CASCADE;
        DROP TABLE IF EXISTS procrastinate_jobs CASCADE;
        """
    )
