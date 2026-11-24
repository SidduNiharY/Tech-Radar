"""The owner's preferences in `user_settings` (Phase 4 Task 2).

One row per `UserSettings` field (`key` = field name, `value` = its JSON). Other keys in the
table (Phase 11's `fsrs_params`) are left alone. A stored value that no longer validates is
ignored and its default used, so one bad row cannot break the Settings screen or the
briefing. `briefing_job` reads `load_user_settings` (briefing time and sections).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.api.schemas import UserSettings
from techradar.briefing.compose import SECTION_ORDER
from techradar.db.models import UserSettings as UserSettingsRow

FIELDS = tuple(UserSettings.model_fields)


def default_settings(briefing_time: str = "06:30") -> UserSettings:
    return UserSettings(briefing_time=briefing_time, sections=list(SECTION_ORDER))


def merge_settings(stored: dict[str, Any], defaults: UserSettings) -> UserSettings:
    """Defaults overlaid with each stored field that still validates."""
    merged = defaults.model_dump(mode="json")
    for key in FIELDS:
        if key not in stored:
            continue
        trial = {**merged, key: stored[key]}
        try:
            UserSettings.model_validate(trial)
        except ValidationError:
            continue
        merged = trial
    return UserSettings.model_validate(merged)


async def load_user_settings(session: AsyncSession, defaults: UserSettings) -> UserSettings:
    rows = (
        await session.execute(
            select(UserSettingsRow.key, UserSettingsRow.value).where(
                UserSettingsRow.key.in_(FIELDS)
            )
        )
    ).all()
    return merge_settings({key: value for key, value in rows}, defaults)


async def save_user_settings(
    session: AsyncSession, new: UserSettings, now: datetime, *, only: set[str] | None = None
) -> None:
    """Upsert the given fields (all when `only` is None). Flushes only; the caller commits."""
    values = new.model_dump(mode="json")
    for key in sorted(only if only is not None else set(FIELDS)):
        if key not in values:
            continue
        stmt = insert(UserSettingsRow).values(key=key, value=values[key], updated_at=now)
        stmt = stmt.on_conflict_do_update(
            index_elements=[UserSettingsRow.key],
            set_={"value": stmt.excluded.value, "updated_at": stmt.excluded.updated_at},
        )
        await session.execute(stmt)
    await session.flush()
