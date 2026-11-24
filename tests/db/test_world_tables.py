"""Phase 7 tables (migration 0009_world): grants, constraints and the models that match."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import EconSeries, Prediction

MIGRATION = Path("src/techradar/db/migrations/versions/0009_world.py")


def test_migration_0009_grants_the_world_tables_and_drops_them_on_downgrade() -> None:
    src = MIGRATION.read_text()
    upgrade, downgrade = src.split("def downgrade", 1)
    assert "GRANT SELECT, INSERT, UPDATE, DELETE" in upgrade and "TO tr_app" in upgrade
    assert "GRANT SELECT ON" in upgrade and "TO tr_ro" in upgrade
    assert "NEW_TABLES" in downgrade and "drop_table" in downgrade
    assert 'down_revision: str | None = "0008_voice"' in src


def test_predictions_model_matches_the_migration() -> None:
    cols = Prediction.__table__.columns
    assert cols["text"].type.length == 280
    assert cols["reminded_at"].nullable
    assert '"reminded_at"' in MIGRATION.read_text()
    names = {c.name for c in Prediction.__table__.constraints}
    assert "ck_predictions_outcome" in names and "ck_predictions_outcome" in MIGRATION.read_text()


@pytest.mark.db
async def test_prediction_outcome_must_be_one_to_three(session: AsyncSession) -> None:
    session.add(Prediction(text="Rates fall", due_date=date(2027, 3, 31), outcome=9))
    with pytest.raises(IntegrityError):
        await session.flush()


@pytest.mark.db
async def test_econ_series_one_value_per_period_and_source(session: AsyncSession) -> None:
    row = {"series": "usd_inr", "period": date(2026, 11, 1), "unit": "", "source_kind": "manual"}
    session.add(EconSeries(value=84.2, **row))
    await session.flush()
    session.add(EconSeries(value=84.3, **row))
    with pytest.raises(IntegrityError):
        await session.flush()
