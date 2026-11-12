"""Outdated fact supersession and subject registry."""

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import Fact, FactSource
from techradar.db.models import FactChange as DbFactChange
from techradar.pipeline.verify import normalize


def load_subjects(path: Path) -> dict[str, list[str]]:
    """Load subject key to aliases mapping from yaml configuration."""
    data: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {k: list(v.get("aliases", [])) for k, v in data.items()}


def load_labels(path: Path) -> dict[str, str]:
    """Load subject key to display label mapping from yaml configuration."""
    data: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {k: str(v.get("label", k)) for k, v in data.items()}


def subject_key(subject: str, aliases: Mapping[str, Sequence[str]]) -> str | None:
    """Find subject key whose normalized alias matches the normalized subject."""
    target = normalize(subject)
    for key, alias_list in aliases.items():
        for alias in alias_list:
            if normalize(alias) == target:
                return key
    return None


class FactChange(BaseModel):
    """Event model representing a superseded factual value change."""

    model_config = ConfigDict(extra="forbid")

    subject_key: str
    old_fact_id: int
    new_fact_id: int
    old_value: str
    new_value: str


def render_fact_change(c: FactChange, label: str) -> str:
    """Format notification message for superseded fact."""
    return f"{label} changed: {c.old_value} → {c.new_value}. Old cards updated."


async def supersede_if_newer(
    session: AsyncSession,
    new_fact_id: int,
    official: frozenset[str],
) -> FactChange | None:
    """Supersede older verified facts if new fact is verified, newer, and officially sourced."""
    stmt = select(Fact).where(Fact.id == new_fact_id)
    res = await session.execute(stmt)
    new_fact = res.scalar_one_or_none()
    if new_fact is None or new_fact.status != "verified" or not new_fact.subject_key:
        return None

    if new_fact.as_of is None:
        return None

    # Verify at least one supported source is on an official domain
    source_stmt = select(FactSource).where(
        and_(
            FactSource.fact_id == new_fact_id,
            FactSource.supported.is_(True),
            FactSource.domain.in_(official),
        )
    )
    source_res = await session.execute(source_stmt)
    if not source_res.scalars().first():
        return None

    # Find candidate earlier verified facts with same subject_key
    other_stmt = (
        select(Fact)
        .where(
            and_(
                Fact.id != new_fact_id,
                Fact.subject_key == new_fact.subject_key,
                Fact.status == "verified",
                Fact.as_of < new_fact.as_of,
            )
        )
        .order_by(Fact.as_of.desc(), Fact.id.desc())
    )
    other_res = await session.execute(other_stmt)
    candidates = other_res.scalars().all()

    # Compare with the most recent earlier fact only: if it already says the same
    # thing, nothing changed (an even older, different value was already replaced
    # by that one, so it must not be superseded again).
    if not candidates:
        return None
    older_fact = candidates[0]
    if normalize(older_fact.value or "") == normalize(new_fact.value or ""):
        return None

    older_fact.status = "superseded"
    older_fact.superseded_by = new_fact_id

    db_change = DbFactChange(
        subject_key=new_fact.subject_key,
        old_fact_id=older_fact.id,
        new_fact_id=new_fact_id,
        old_value=older_fact.value,
        new_value=new_fact.value,
    )
    session.add(db_change)
    await session.flush()

    return FactChange(
        subject_key=new_fact.subject_key,
        old_fact_id=older_fact.id,
        new_fact_id=new_fact_id,
        old_value=older_fact.value or "",
        new_value=new_fact.value or "",
    )
