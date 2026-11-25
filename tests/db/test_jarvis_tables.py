from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import DataError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import GpuLease, JarvisSession, JarvisTurn, JarvisWrite

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


async def test_session_device_must_be_known(session: AsyncSession):
    session.add(JarvisSession(device="toaster"))
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_turn_role_must_be_me_or_jarvis(session: AsyncSession):
    sess = JarvisSession(device="mac")
    session.add(sess)
    await session.flush()
    session.add(JarvisTurn(session_id=sess.id, role="stranger", text="hi"))
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_write_status_must_be_known(session: AsyncSession):
    session.add(
        JarvisWrite(
            ticket_id=2**40,  # pending_actions.id is a bigint
            action="jarvis.plan_add",
            args={},
            summary="Add 60 minutes of polity.",
            status="maybe",
        )
    )
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_ticket_ids_are_bigint(session: AsyncSession):
    sess = JarvisSession(device="phone")
    session.add(sess)
    await session.flush()
    turn = JarvisTurn(session_id=sess.id, role="jarvis", text="ok", ticket_id=2**40)
    session.add(turn)
    await session.flush()
    assert turn.id is not None
