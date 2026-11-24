"""Tickets without a database (Phase 4 Task 2b). SEC-56. The db side is tests/test_tickets.py."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy.dialects import postgresql

from techradar import tickets
from techradar.tickets import (
    ACTIONS,
    TTL_S,
    args_hash,
    claim_statement,
    confirm_ticket,
    create_ticket,
    run_confirmed,
)

NOW = datetime(2026, 11, 22, 9, 0, tzinfo=UTC)


class NoDb:
    """A session that must not be used."""

    async def execute(self, *_a: Any, **_k: Any) -> Any:
        raise AssertionError("no query expected")


def test_args_hash_is_the_plan_formula() -> None:
    expected = hashlib.sha256(
        json.dumps(
            {"action": "a", "args": {"b": 1, "a": 2}}, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()
    assert args_hash("a", {"b": 1, "a": 2}) == expected
    assert args_hash("a", {"a": 2, "b": 1}) == expected  # key order does not matter
    assert args_hash("b", {"a": 2, "b": 1}) != expected
    assert args_hash("a", {"a": 2, "b": 2}) != expected


def test_ttls() -> None:
    assert TTL_S == {"web": 60, "telegram": 60, "voice": 10}


def test_the_claim_is_one_conditional_update() -> None:
    sql = str(
        claim_statement("a" * 32, "web:x", "h" * 64, NOW).compile(dialect=postgresql.dialect())
    )
    assert sql.startswith("UPDATE techradar.pending_actions SET used_at=")
    for cond in (
        "pending_actions.token =",
        "pending_actions.used_at IS NULL",
        "pending_actions.cancelled_at IS NULL",
        "pending_actions.expires_at >",
        "pending_actions.session_id =",
        "pending_actions.args_hash =",
        "RETURNING techradar.pending_actions.id",
    ):
        assert cond in sql, cond


@pytest.mark.parametrize("token", ["", "A" * 32, "a" * 31, "a" * 33, "g" * 32, "' OR 1=1 --"])
async def test_a_malformed_token_is_unknown_without_a_query(token: str) -> None:
    assert (
        await confirm_ticket(NoDb(), token=token, session_id="web:a", action="a", args={}, now=NOW)  # type: ignore[arg-type]
        == "unknown"
    )
    assert await run_confirmed(NoDb(), token, "web:a", NOW) == ("unknown", None)  # type: ignore[arg-type]


async def test_create_refuses_bad_input() -> None:
    bad: list[dict[str, Any]] = [
        {"channel": "email"},
        {"session_id": ""},
        {"action": ""},
        {"args": {"x": 1.5}},  # floats do not survive jsonb unchanged
        {"args": {"x": object()}},
        {"args": {1: "int key"}},
    ]
    for override in bad:
        kw: dict[str, Any] = {
            "session_id": "web:a",
            "channel": "web",
            "action": "a",
            "args": {},
            "summary": "s",
            "now": NOW,
        } | override
        with pytest.raises((ValueError, TypeError)):
            await create_ticket(NoDb(), **kw)  # type: ignore[arg-type]


def test_this_phase_registers_the_quarantine_actions() -> None:
    assert {"quarantine.release", "quarantine.delete"} <= set(ACTIONS)


def test_session_ids() -> None:
    assert tickets.tg_session_id(42) == "tg:42"
    assert tickets.web_session_id("abcDEF0123456789_-") == "web:abcDEF0123456789_-"
    for bad in (None, "", "short", "x" * 65, "has space 123456789", "tg:12345678901234"):
        assert tickets.web_session_id(bad) is None
