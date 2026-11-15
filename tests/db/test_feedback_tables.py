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
