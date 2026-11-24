"""/econ: owner-only routing and the handler (SEC-26)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from techradar.bot import econ
from techradar.bot.routing import Routed, route_update

OWNER = 42


def test_econ_is_the_owners_alone() -> None:
    assert route_update(OWNER, "/econ", OWNER) == Routed("econ", "")
    assert route_update(OWNER, "/econ@bot usd_inr 2026-11 84.2", OWNER) == Routed(
        "econ", "usd_inr 2026-11 84.2"
    )
    assert route_update(7, "/econ", OWNER) == Routed("ignore")
    assert route_update(-100, "/econ usd_inr 2026-11 1", OWNER, group_ids={-100}) == Routed(
        "ignore"
    )


def _setup() -> tuple[MagicMock, dict, MagicMock]:
    session = MagicMock()
    session.commit = AsyncMock()

    @asynccontextmanager
    async def factory():
        yield session

    update = MagicMock()
    update.message.reply_text = AsyncMock()
    return update, {"session_factory": factory}, session


async def test_econ_alone_reads_the_stored_series(monkeypatch: pytest.MonkeyPatch) -> None:
    render = AsyncMock(return_value="Repo rate stayed at 5.5%.")
    monkeypatch.setattr(econ, "render_econ", render)
    update, data, session = _setup()
    await econ.handle_econ(update, data, "")
    render.assert_awaited_once_with(session)
    update.message.reply_text.assert_awaited_once_with("Repo rate stayed at 5.5%.")


async def test_econ_with_values_saves_a_manual_series(monkeypatch: pytest.MonkeyPatch) -> None:
    record = AsyncMock()
    monkeypatch.setattr(econ, "record_manual", record)
    update, data, session = _setup()
    await econ.handle_econ(update, data, "usd_inr 2026-11 84.2")
    record.assert_awaited_once_with(session, "usd_inr", date(2026, 11, 1), 84.2)
    session.commit.assert_awaited_once()
    update.message.reply_text.assert_awaited_once_with("Saved.")


async def test_a_bad_econ_command_saves_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    record = AsyncMock()
    monkeypatch.setattr(econ, "record_manual", record)
    update, data, session = _setup()
    await econ.handle_econ(update, data, "repo_rate 2026-11 9")
    record.assert_not_awaited()
    assert update.message.reply_text.call_args.args[0].startswith("Unknown series")
    session.commit.assert_not_awaited()
