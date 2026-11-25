"""Model registry: which Ollama tag serves each role, and the log of changes (Phase 10 Task 1).

SEC: SEC-23, SEC-30.

This is the DATA side only. `set_role_model` and `rollback` check the rules, write the
registry row, the `model_changes` row and an `audit_log` row, and send `NOTIFY model_changed`.
They never pull or load a model and never talk to Ollama: the caller passes in the set of
installed tags.

WIRING(claude, Opus, later): the parts that change what the system runs are not built here:
  - the owner's typed confirmation `"<role>:<tag>"` and the one-time ticket (`models.change`,
    `models.rollback`; SEC-56, phase 4 Task 2b),
  - the API routes and the admin screen (Task 5),
  - reading `/api/tags` to build `installed`, and `make pull-approved` (Task 2),
  - the worker `LISTEN model_changed` that rebuilds its router from `load_roles_from_db`.
Until those exist nothing calls `set_role_model`, so no running model changes.
"""

from __future__ import annotations

from collections.abc import Collection
from pathlib import Path

from pydantic import BaseModel, ValidationError
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import AuditEvent, ModelChange, ModelRegistry, ModelTest
from techradar.llm.roles import Role, RoleConfigError, RoleModel, load_roles

DEFAULT_ROLES_PATH = Path("infra/models/roles.yaml")
NOTIFY_CHANNEL = "model_changed"
PULL_FIRST = "Pull it first (make pull-approved)"


class ChangeResult(BaseModel):
    ok: bool
    message: str
    change_id: int | None = None


def _refuse(message: str) -> ChangeResult:
    return ChangeResult(ok=False, message=message, change_id=None)


async def current_model(
    session: AsyncSession, role: Role, fallback: Path = DEFAULT_ROLES_PATH
) -> tuple[str, str]:
    """(tag, family) now serving `role`: the registry row, else the `roles.yaml` seed."""
    row = await session.get(ModelRegistry, role.value)
    if row is not None:
        return row.ollama_tag, row.family
    seed = load_roles(fallback)[role]
    return seed.ollama_tag, seed.family


async def _family_conflict(
    session: AsyncSession, role: Role, family: str, fallback: Path
) -> str | None:
    """The independent-checker rule: worker and checker must not share a family."""
    if role not in (Role.WORKER, Role.CHECKER):
        return None
    other = Role.CHECKER if role is Role.WORKER else Role.WORKER
    _, other_family = await current_model(session, other, fallback)
    if family == other_family:
        return f"Family conflict: worker and checker cannot both be '{family}'"
    return None


async def _apply(
    session: AsyncSession,
    role: Role,
    tag: str,
    family: str,
    *,
    action: str,
    actor: str,
    detail: dict[str, object],
) -> None:
    """Write the registry row, the audit row (SEC-30) and the NOTIFY."""
    row = await session.get(ModelRegistry, role.value)
    if row is None:
        session.add(ModelRegistry(role=role.value, ollama_tag=tag, family=family))
    else:
        row.ollama_tag = tag
        row.family = family
        await session.flush()
        await session.execute(
            text("UPDATE techradar.model_registry SET updated_at = now() WHERE role = :r"),
            {"r": role.value},
        )
    session.add(AuditEvent(actor=actor[:64], action=action, detail=detail))
    await session.execute(
        text("SELECT pg_notify(:channel, :payload)"),
        {"channel": NOTIFY_CHANNEL, "payload": role.value},
    )


async def set_role_model(
    session: AsyncSession,
    role: Role,
    tag: str,
    family: str,
    *,
    test_id: int,
    actor: str,
    reason: str,
    installed: Collection[str],
    fallback: Path = DEFAULT_ROLES_PATH,
) -> ChangeResult:
    """Record a switch of `role` to `tag` after the three checks; the caller commits."""
    try:
        RoleModel(ollama_tag=tag, family=family, num_ctx=8192)
    except ValidationError:
        return _refuse("Invalid model tag or family")
    if not actor.strip():
        return _refuse("An actor is required")

    # 1. installed (the approved-list check belongs to the caller, Task 2)
    if tag not in installed:
        return _refuse(PULL_FIRST)

    # 2. a passed test for exactly this role and tag
    test = await session.get(ModelTest, test_id)
    if test is None or test.role != role.value or test.tag != tag or not test.passed:
        return _refuse("No passed test for this role and tag")

    # 3. the family rule
    conflict = await _family_conflict(session, role, family, fallback)
    if conflict is not None:
        return _refuse(conflict)

    old_tag, old_family = await current_model(session, role, fallback)
    if old_tag == tag:
        return _refuse("That model is already in use")

    change = ModelChange(
        role=role.value,
        old_tag=old_tag,
        new_tag=tag,
        old_family=old_family,
        new_family=family,
        test_id=test_id,
        actor=actor,
        reason=reason,
    )
    session.add(change)
    await session.flush()
    await _apply(
        session,
        role,
        tag,
        family,
        action="model.change",
        actor=actor,
        detail={"role": role.value, "old": old_tag, "new": tag, "change_id": change.id},
    )
    await session.flush()
    return ChangeResult(ok=True, message=f"{role.value} is now {tag}", change_id=change.id)


async def rollback(
    session: AsyncSession, change_id: int, actor: str, fallback: Path = DEFAULT_ROLES_PATH
) -> ChangeResult:
    """Undo the latest change of a role: restore the old tag and mark the change rolled back."""
    change = await session.get(ModelChange, change_id)
    if change is None:
        return _refuse("No such change")
    if change.rolled_back:
        return _refuse("Already rolled back")
    if not actor.strip():
        return _refuse("An actor is required")

    role = Role(change.role)
    tag, _ = await current_model(session, role, fallback)
    if tag != change.new_tag:
        return _refuse("Only the latest change of a role can be rolled back")

    old_family = change.old_family
    if old_family is None:
        return _refuse("This change has no recorded family to restore")
    conflict = await _family_conflict(session, role, old_family, fallback)
    if conflict is not None:
        return _refuse(conflict)

    change.rolled_back = True
    await _apply(
        session,
        role,
        change.old_tag,
        old_family,
        action="model.rollback",
        actor=actor,
        detail={"role": role.value, "restored": change.old_tag, "change_id": change.id},
    )
    await session.flush()
    return ChangeResult(
        ok=True, message=f"{role.value} is back to {change.old_tag}", change_id=change.id
    )


async def load_roles_from_db(session: AsyncSession, fallback: Path) -> dict[Role, RoleModel]:
    """Roles from the Postgres registry; `roles.yaml` is the seed and the fallback.

    Registry rows override only the tag and family; context size, thinking and provider stay
    from the yaml. With an empty registry the result equals `load_roles(fallback)`. The
    worker/checker family rule is checked again on the merged result.

    It lives here, not in `llm/roles.py` as the plan said: the reader imports `llm.roles`, and
    import contract 2 (reader isolation) forbids that module from reaching `techradar.db`.
    """
    roles = load_roles(fallback)
    rows = (await session.execute(select(ModelRegistry))).scalars().all()
    for row in rows:
        try:
            role = Role(row.role)
        except ValueError:
            continue  # a role this version does not know
        roles[role] = roles[role].model_copy(
            update={"ollama_tag": row.ollama_tag, "family": row.family}
        )
    if roles[Role.WORKER].family == roles[Role.CHECKER].family:
        family = roles[Role.WORKER].family
        raise RoleConfigError(
            f"family conflict: worker and checker cannot share family ('{family}')"
        )
    return roles


async def list_changes(session: AsyncSession, limit: int = 50) -> list[ModelChange]:
    """The change log, newest first (History tab)."""
    rows = await session.execute(select(ModelChange).order_by(ModelChange.id.desc()).limit(limit))
    return list(rows.scalars())
