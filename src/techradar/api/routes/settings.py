"""`GET` and `PUT /v1/settings`: briefing time, sections, verified-only default.

A PUT stores only the fields the request names, so the Settings screen cannot reset the
planner's fields (Phase 5) by leaving them out.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import ValidationError

from techradar.api.deps import AppSession, AppSettings, Now, RoSession
from techradar.api.schemas import UserSettings
from techradar.settings import Settings
from techradar.user_settings import default_settings, load_user_settings, save_user_settings

router = APIRouter(prefix="/settings", tags=["settings"])


def _defaults(settings: Settings) -> UserSettings:
    try:
        return default_settings(settings.briefing_time)
    except ValidationError:
        return default_settings()


@router.get("", response_model=UserSettings)
async def read_settings(session: RoSession, settings: AppSettings) -> UserSettings:
    return await load_user_settings(session, _defaults(settings))


@router.put("", response_model=UserSettings)
async def write_settings(
    body: UserSettings, session: AppSession, now: Now, settings: AppSettings
) -> UserSettings:
    await save_user_settings(session, body, now, only=set(body.model_fields_set))
    await session.commit()
    return await load_user_settings(session, _defaults(settings))
