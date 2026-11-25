"""Model registry: switches, rollback, audit and the DB loader (Phase 10 Task 1).

The `db` tests need Postgres with migration 0012 (the server); the others run anywhere.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import AuditEvent, ModelChange, ModelRegistry, ModelTest
from techradar.llm.roles import Role, RoleConfigError
from techradar.models.registry import (
    PULL_FIRST,
    ChangeResult,
    current_model,
    list_changes,
    load_roles_from_db,
    rollback,
    set_role_model,
)

ROLES_YAML = Path("infra/models/roles.yaml")
ALL_INSTALLED = {"qwen3.5:4b", "qwen3.5:9b", "gemma4:e2b-it-qat", "gemma4:e4b-it-qat"}


async def _clean(session: AsyncSession) -> None:
    """Tests share a database; clear what the registry tests write (rolled back after)."""
    await session.execute(text("DELETE FROM techradar.model_registry"))
    await session.execute(text("DELETE FROM techradar.model_changes"))


async def _passed_test(session: AsyncSession, role: Role, tag: str, passed: bool = True) -> int:
    test = ModelTest(role=role.value, tag=tag, metrics={}, passed=passed)
    session.add(test)
    await session.flush()
    return test.id


# --- no database needed: refusals that happen before any query ------------------------


async def test_not_installed_refused_before_any_query() -> None:
    r = await set_role_model(
        None,  # type: ignore[arg-type]  # never touched: the installed check comes first
        Role.WORKER,
        "qwen3.5:9b",
        "qwen",
        test_id=1,
        actor="me",
        reason="t",
        installed={"qwen3.5:4b"},
    )
    assert r == ChangeResult(ok=False, message=PULL_FIRST, change_id=None)
    assert PULL_FIRST == "Pull it first (make pull-approved)"


async def test_invalid_tag_refused() -> None:
    r = await set_role_model(
        None,  # type: ignore[arg-type]
        Role.WORKER,
        "Bad Tag!",
        "qwen",
        test_id=1,
        actor="me",
        reason="t",
        installed={"Bad Tag!"},
    )
    assert not r.ok and "Invalid" in r.message


async def test_actor_required() -> None:
    r = await set_role_model(
        None,  # type: ignore[arg-type]
        Role.WORKER,
        "qwen3.5:9b",
        "qwen",
        test_id=1,
        actor=" ",
        reason="t",
        installed={"qwen3.5:9b"},
    )
    assert not r.ok


# --- database tests -------------------------------------------------------------------

db = pytest.mark.db


@db
async def test_switch_requires_installed(session: AsyncSession) -> None:
    r = await set_role_model(
        session,
        Role.WORKER,
        "qwen3.5:9b",
        "qwen",
        test_id=1,
        actor="me",
        reason="t",
        installed={"qwen3.5:4b"},
    )
    assert not r.ok and r.message == "Pull it first (make pull-approved)"


@db
async def test_switch_requires_passed_test(session: AsyncSession) -> None:
    await _clean(session)
    failed = await _passed_test(session, Role.WORKER, "qwen3.5:9b", passed=False)
    wrong_role = await _passed_test(session, Role.CHECKER, "qwen3.5:9b")
    wrong_tag = await _passed_test(session, Role.WORKER, "qwen3.5:4b")
    for test_id in (failed, wrong_role, wrong_tag, 999_999_999):
        r = await set_role_model(
            session,
            Role.WORKER,
            "qwen3.5:9b",
            "qwen",
            test_id=test_id,
            actor="me",
            reason="t",
            installed=ALL_INSTALLED,
        )
        assert not r.ok and "passed test" in r.message
    assert (await session.get(ModelRegistry, "worker")) is None  # nothing was written


@db
async def test_family_rule_enforced(session: AsyncSession) -> None:
    await _clean(session)  # seed: checker is gemma
    test_id = await _passed_test(session, Role.WORKER, "gemma4:e4b-it-qat")
    r = await set_role_model(
        session,
        Role.WORKER,
        "gemma4:e4b-it-qat",
        "gemma",
        test_id=test_id,
        actor="me",
        reason="t",
        installed=ALL_INSTALLED,
    )
    assert not r.ok and "Family conflict" in r.message
    assert await session.scalar(select(ModelChange.id)) is None


@db
async def test_switch_writes_registry_change_and_audit(session: AsyncSession) -> None:
    await _clean(session)
    test_id = await _passed_test(session, Role.WORKER, "qwen3.5:9b")
    r = await set_role_model(
        session,
        Role.WORKER,
        "qwen3.5:9b",
        "qwen",
        test_id=test_id,
        actor="me@tailnet",
        reason="better tags",
        installed=ALL_INSTALLED,
    )
    assert r.ok and r.change_id is not None
    assert await current_model(session, Role.WORKER) == ("qwen3.5:9b", "qwen")
    change = await session.get(ModelChange, r.change_id)
    assert change is not None
    assert (change.old_tag, change.new_tag, change.actor) == (
        "qwen3.5:4b",
        "qwen3.5:9b",
        "me@tailnet",
    )
    audit = (
        await session.execute(select(AuditEvent).where(AuditEvent.action == "model.change"))
    ).scalars()
    assert any(a.actor == "me@tailnet" and a.detail["change_id"] == r.change_id for a in audit)
    assert [c.id for c in await list_changes(session)][0] == r.change_id


@db
async def test_same_model_refused(session: AsyncSession) -> None:
    await _clean(session)
    test_id = await _passed_test(session, Role.WORKER, "qwen3.5:4b")
    r = await set_role_model(
        session,
        Role.WORKER,
        "qwen3.5:4b",
        "qwen",
        test_id=test_id,
        actor="me",
        reason="t",
        installed=ALL_INSTALLED,
    )
    assert not r.ok


@db
async def test_rollback_restores_previous(session: AsyncSession) -> None:
    await _clean(session)
    test_id = await _passed_test(session, Role.WORKER, "qwen3.5:9b")
    r = await set_role_model(
        session,
        Role.WORKER,
        "qwen3.5:9b",
        "qwen",
        test_id=test_id,
        actor="me",
        reason="t",
        installed=ALL_INSTALLED,
    )
    assert r.change_id is not None
    back = await rollback(session, r.change_id, "me")
    assert back.ok
    assert await current_model(session, Role.WORKER) == ("qwen3.5:4b", "qwen")
    change = await session.get(ModelChange, r.change_id)
    assert change is not None and change.rolled_back
    again = await rollback(session, r.change_id, "me")
    assert not again.ok and "Already" in again.message


@db
async def test_only_latest_change_rolls_back(session: AsyncSession) -> None:
    await _clean(session)
    ids: list[int] = []
    for tag in ("qwen3.5:9b", "qwen3.5:4b"):
        test_id = await _passed_test(session, Role.WORKER, tag)
        r = await set_role_model(
            session,
            Role.WORKER,
            tag,
            "qwen",
            test_id=test_id,
            actor="me",
            reason="t",
            installed=ALL_INSTALLED,
        )
        assert r.ok and r.change_id is not None
        ids.append(r.change_id)
    first = await rollback(session, ids[0], "me")
    assert not first.ok and "latest" in first.message


@db
async def test_rollback_unknown_change(session: AsyncSession) -> None:
    r = await rollback(session, 999_999_999, "me")
    assert not r.ok


@db
async def test_load_roles_from_db_falls_back_then_overrides(session: AsyncSession) -> None:
    await _clean(session)
    seeded = await load_roles_from_db(session, ROLES_YAML)
    assert seeded[Role.WORKER].ollama_tag == "qwen3.5:4b"
    session.add(ModelRegistry(role="worker", ollama_tag="qwen3.5:9b", family="qwen"))
    await session.flush()
    merged = await load_roles_from_db(session, ROLES_YAML)
    assert merged[Role.WORKER].ollama_tag == "qwen3.5:9b"
    assert merged[Role.WORKER].num_ctx == seeded[Role.WORKER].num_ctx  # only tag and family


@db
async def test_load_roles_from_db_rejects_family_clash(session: AsyncSession) -> None:
    await _clean(session)
    session.add(ModelRegistry(role="worker", ollama_tag="gemma4:e4b-it-qat", family="gemma"))
    await session.flush()
    with pytest.raises(RoleConfigError):
        await load_roles_from_db(session, ROLES_YAML)
