from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import Feedback, Weight

pytestmark = pytest.mark.db


async def test_feedback_unique_per_day(session: AsyncSession):
    now = datetime.now(UTC)
    today = date(2026, 11, 15)
    f1 = Feedback(
        target_kind="note",
        target_id=1,
        signal="thumbs_up",
        actor="web",
        day=today,
        at=now,
    )
    session.add(f1)
    await session.flush()

    f2 = Feedback(
        target_kind="note",
        target_id=1,
        signal="thumbs_up",
        actor="telegram",
        day=today,
        at=now,
    )
    session.add(f2)
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_weights_primary_key(session: AsyncSession):
    now = datetime.now(UTC)
    w1 = Weight(kind="topic", key="entity:crypto", value=1.0, updated_at=now)
    session.add(w1)
    await session.flush()

    w2 = Weight(kind="topic", key="entity:crypto", value=0.8, updated_at=now)
    session.add(w2)
    with pytest.raises(IntegrityError):
        await session.flush()


def test_migration_0013_grants_the_feedback_tables() -> None:
    from pathlib import Path

    src = Path("src/techradar/db/migrations/versions/0013_feedback.py").read_text()
    upgrade, downgrade = src.split("def downgrade", 1)
    assert "GRANT SELECT, INSERT, UPDATE, DELETE" in upgrade and "TO tr_app" in upgrade
    assert "GRANT SELECT ON" in upgrade and "TO tr_ro" in upgrade
    assert "drop_table" in downgrade


@pytest.fixture
async def ro_conn(db_settings):
    from techradar.db.engine import make_engine

    engine = make_engine("ro", db_settings)
    async with engine.connect() as conn:
        await conn.execution_options(isolation_level="AUTOCOMMIT")
        yield conn
    await engine.dispose()


async def test_ro_cannot_write_rules(ro_conn) -> None:
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    with pytest.raises(DBAPIError, match="permission denied"):
        await ro_conn.execute(
            text(
                "INSERT INTO techradar.preference_rules (field, value, evidence, status) "
                "VALUES ('length', 'short', '{}', 'active')"
            )
        )
