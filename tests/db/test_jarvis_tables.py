from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import DataError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import GpuLease, JarvisSession, JarvisTurn

pytestmark = pytest.mark.db


async def test_gpu_lease_single_row(session: AsyncSession):
    lease2 = GpuLease(id=2, holder="someone")
    session.add(lease2)
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_turn_text_length_limited(session: AsyncSession):
    now = datetime.now(UTC)
    sess = JarvisSession(device="mac", started_at=now)
    session.add(sess)
    await session.flush()

    long_text = "A" * 2001
    turn = JarvisTurn(
        session_id=sess.id,
        role="me",
        text=long_text,
        created_at=now,
    )
    session.add(turn)
    with pytest.raises((DataError, IntegrityError)):
        await session.flush()
