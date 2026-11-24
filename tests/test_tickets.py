"""One-time confirmation tickets in `pending_actions` (Phase 4 Task 2b). SEC-56, D43.

Marker `db`: needs the dev Postgres (127.0.0.1:55432) and ./secrets; run with `make test-db`.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncGenerator, Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from techradar.db.engine import database_url
from techradar.db.models import PendingAction
from techradar.settings import Settings
from techradar.tickets import (
    confirm_ticket,
    create_ticket,
    open_window,
    run_confirmed,
)

pytestmark = pytest.mark.db

NOW = datetime(2026, 11, 22, 9, 0, tzinfo=UTC)


def _settings() -> Settings:
    return Settings(
        telegram_owner_chat_id=1,
        db_host="127.0.0.1",
        db_port=55432,
        db_name="techradar",
        secrets_dir=Path("secrets"),
    )


def _factory(role: str = "app") -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(database_url(role, _settings()), poolclass=NullPool)  # type: ignore[arg-type]
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
async def session() -> AsyncGenerator[AsyncSession]:
    """A session whose changes are rolled back after the test."""
    async with _factory()() as s:
        yield s
        await s.rollback()


@pytest.fixture
async def committed() -> AsyncGenerator[async_sessionmaker[AsyncSession]]:
    """For tests that need two connections: pending_actions is emptied around them."""
    if os.environ.get("TR_DB_TESTS_MAY_WIPE") != "1":
        pytest.skip("set TR_DB_TESTS_MAY_WIPE=1 (make test-db does) to allow wiping test tables")

    async def wipe() -> None:
        async with _factory("migrator")() as s:
            await s.execute(text("TRUNCATE techradar.pending_actions RESTART IDENTITY"))
            await s.commit()

    await wipe()
    yield _factory()
    await wipe()


# --- the plan's tests ---------------------------------------------------------------------


async def test_ticket_runs_once(session):
    t = await create_ticket(
        session,
        session_id="web:a",
        channel="web",
        action="quarantine.delete",
        args={"id": 1},
        summary="Delete x",
        now=NOW,
    )
    assert (
        await confirm_ticket(
            session,
            token=t.token,
            session_id="web:a",
            action="quarantine.delete",
            args={"id": 1},
            now=NOW,
        )
        == "ok"
    )
    assert (
        await confirm_ticket(
            session,
            token=t.token,
            session_id="web:a",
            action="quarantine.delete",
            args={"id": 1},
            now=NOW,
        )
        == "used"
    )


async def test_ticket_expires(session):
    t = await create_ticket(
        session, session_id="web:a", channel="web", action="a", args={}, summary="s", now=NOW
    )
    assert (
        await confirm_ticket(
            session,
            token=t.token,
            session_id="web:a",
            action="a",
            args={},
            now=NOW + timedelta(seconds=61),
        )
        == "expired"
    )


async def test_ticket_other_session_refused(session):
    t = await create_ticket(
        session, session_id="web:a", channel="web", action="a", args={}, summary="s", now=NOW
    )
    assert (
        await confirm_ticket(
            session, token=t.token, session_id="web:b", action="a", args={}, now=NOW
        )
        == "wrong_session"
    )


async def test_ticket_tampered_args_refused(session):
    t = await create_ticket(
        session,
        session_id="web:a",
        channel="web",
        action="a",
        args={"minutes": 60},
        summary="s",
        now=NOW,
    )
    assert (
        await confirm_ticket(
            session, token=t.token, session_id="web:a", action="a", args={"minutes": 600}, now=NOW
        )
        == "tampered"
    )


async def test_new_ticket_cancels_old(session):
    t1 = await create_ticket(
        session, session_id="web:a", channel="web", action="a", args={}, summary="1", now=NOW
    )
    await create_ticket(
        session, session_id="web:a", channel="web", action="b", args={}, summary="2", now=NOW
    )
    assert (
        await confirm_ticket(
            session, token=t1.token, session_id="web:a", action="a", args={}, now=NOW
        )
        == "cancelled"
    )


async def test_voice_window_starts_when_opened(session):
    t = await create_ticket(
        session,
        session_id="voice:1",
        channel="voice",
        action="a",
        args={},
        summary="s",
        now=NOW,
        starts_at=NOW + timedelta(seconds=30),
    )
    await open_window(session, t.id, at=NOW + timedelta(seconds=8))
    assert (
        await confirm_ticket(
            session,
            token=t.token,
            session_id="voice:1",
            action="a",
            args={},
            now=NOW + timedelta(seconds=17),
        )
        == "ok"
    )


# --- more -------------------------------------------------------------------------------


async def test_another_action_with_the_same_ticket_is_tampered(session):
    t = await create_ticket(
        session,
        session_id="web:a",
        channel="web",
        action="quarantine.delete",
        args={"id": 1},
        summary="s",
        now=NOW,
    )
    assert (
        await confirm_ticket(
            session,
            token=t.token,
            session_id="web:a",
            action="quarantine.release",
            args={"id": 1},
            now=NOW,
        )
        == "tampered"
    )
    # a refused attempt does not use the ticket up
    assert (
        await confirm_ticket(
            session,
            token=t.token,
            session_id="web:a",
            action="quarantine.delete",
            args={"id": 1},
            now=NOW,
        )
        == "ok"
    )


async def test_unknown_token(session):
    for unknown in ("0" * 32, "not-a-token"):
        result = await confirm_ticket(
            session, token=unknown, session_id="web:a", action="a", args={}, now=NOW
        )
        assert result == "unknown"


async def test_ticket_is_valid_until_its_last_second(session):
    t = await create_ticket(
        session, session_id="tg:1", channel="telegram", action="a", args={}, summary="s", now=NOW
    )
    assert t.expires_at == NOW + timedelta(seconds=60)
    assert (
        await confirm_ticket(
            session,
            token=t.token,
            session_id="tg:1",
            action="a",
            args={},
            now=NOW + timedelta(seconds=60),
        )
        == "expired"
    )
    t2 = await create_ticket(
        session, session_id="tg:1", channel="telegram", action="a", args={}, summary="s", now=NOW
    )
    assert (
        await confirm_ticket(
            session,
            token=t2.token,
            session_id="tg:1",
            action="a",
            args={},
            now=NOW + timedelta(seconds=59),
        )
        == "ok"
    )


async def test_open_window_cannot_revive_a_used_ticket(session):
    t = await create_ticket(
        session, session_id="voice:1", channel="voice", action="a", args={}, summary="s", now=NOW
    )
    assert (
        await confirm_ticket(
            session, token=t.token, session_id="voice:1", action="a", args={}, now=NOW
        )
        == "ok"
    )
    await open_window(session, t.id, at=NOW + timedelta(seconds=5))
    row = (
        await session.execute(select(PendingAction).where(PendingAction.id == t.id))
    ).scalar_one()  # noqa: E501
    assert row.expires_at == NOW + timedelta(seconds=10)


async def test_run_confirmed_runs_the_stored_action_once(session):
    ran: list[Mapping[str, Any]] = []

    async def act(_s: AsyncSession, args: Mapping[str, Any]) -> str:
        ran.append(args)
        return "Done."

    actions = {"test.act": act}
    t = await create_ticket(
        session,
        session_id="web:a",
        channel="web",
        action="test.act",
        args={"id": 7},
        summary="s",
        now=NOW,
    )
    assert await run_confirmed(session, t.token, "web:a", NOW, actions=actions) == ("ok", "Done.")
    assert await run_confirmed(session, t.token, "web:a", NOW, actions=actions) == ("used", None)
    assert await run_confirmed(session, t.token, "web:b", NOW, actions=actions) == (
        "wrong_session",
        None,
    )
    assert ran == [{"id": 7}]


async def test_run_confirmed_refuses_an_unregistered_action(session):
    t = await create_ticket(
        session,
        session_id="web:a",
        channel="web",
        action="not.registered",
        args={},
        summary="s",
        now=NOW,
    )
    assert await run_confirmed(session, t.token, "web:a", NOW, actions={}) == ("unknown", None)
    # and it was not used up
    assert (
        await confirm_ticket(
            session, token=t.token, session_id="web:a", action="not.registered", args={}, now=NOW
        )
        == "ok"
    )


async def test_a_ticket_is_confirmed_once_under_concurrency(committed):
    async with committed() as s:
        t = await create_ticket(
            s, session_id="web:a", channel="web", action="a", args={}, summary="s", now=NOW
        )
        await s.commit()

    async def confirm() -> str:
        async with committed() as s:
            result = await confirm_ticket(
                s, token=t.token, session_id="web:a", action="a", args={}, now=NOW
            )
            await asyncio.sleep(0.05)
            await s.commit()
            return result

    results = await asyncio.gather(*(confirm() for _ in range(5)))
    assert sorted(results) == ["ok", "used", "used", "used", "used"]


async def test_one_open_ticket_per_session_is_enforced_by_the_database(session):
    await create_ticket(
        session, session_id="web:a", channel="web", action="a", args={}, summary="s", now=NOW
    )
    session.add(
        PendingAction(
            token="f" * 32,
            session_id="web:a",
            channel="web",
            action="b",
            args={},
            args_hash="0" * 64,
            summary="s",
            created_at=NOW,
            expires_at=NOW,
        )  # fmt: skip
    )
    with pytest.raises(DBAPIError):
        await session.flush()


async def test_unknown_channel_is_refused_by_the_database(session):
    session.add(
        PendingAction(
            token="e" * 32,
            session_id="x:1",
            channel="email",
            action="a",
            args={},
            args_hash="0" * 64,
            summary="s",
            created_at=NOW,
            expires_at=NOW,
        )  # fmt: skip
    )
    with pytest.raises(DBAPIError):
        await session.flush()


async def test_read_only_role_cannot_read_ticket_tokens():
    async with _factory("ro")() as s:
        with pytest.raises(DBAPIError, match="permission denied"):
            await s.execute(text("SELECT token FROM techradar.pending_actions LIMIT 1"))
