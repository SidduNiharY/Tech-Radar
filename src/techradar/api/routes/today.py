"""`GET /v1/today`: the latest briefing's stories and today's plan lines (read-only)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter
from pydantic import ValidationError
from sqlalchemy import select

from techradar.api.deps import AppSettings, Now, RoSession
from techradar.api.schemas import FourQuestionsOut, TodayItem, TodayResponse
from techradar.db.models import Briefing, Plan

router = APIRouter(tags=["today"])

MAX_ITEMS = 30
MAX_PLAN_LINES = 20
_FOUR = ("what_happened", "why", "what_changes", "how_it_affects_me")


def today_item(raw: object) -> TodayItem | None:
    """One stored briefing item as a TodayItem, or None when it does not fit.

    Takes the plan's `four_questions` mapping, or the flat `why` / `how_it_affects_me` that
    Phase 3's StoryCandidate stores today.
    """
    if not isinstance(raw, Mapping):
        return None
    four_raw = raw.get("four_questions")
    source: Mapping[str, Any] = four_raw if isinstance(four_raw, Mapping) else raw
    four = {k: source[k] for k in _FOUR if isinstance(source.get(k), str)}
    cluster = raw.get("cluster_id")
    note = raw.get("note_path")
    try:
        return TodayItem(
            cluster_id=str(cluster) if isinstance(cluster, int | str) else "",
            title=raw.get("title"),  # type: ignore[arg-type]
            section=raw.get("section"),  # type: ignore[arg-type]
            exam_tags=[t for t in raw.get("exam_tags") or [] if isinstance(t, str)],
            verified_headline=raw.get("verified_headline") is True,
            four_questions=FourQuestionsOut(**four),
            note_path=note if isinstance(note, str) else None,
        )
    except ValidationError, TypeError:
        return None


@router.get("/today", response_model=TodayResponse)
async def today(session: RoSession, now: Now, settings: AppSettings) -> TodayResponse:
    local_today = now.astimezone(ZoneInfo(settings.tz)).date()
    briefing = (
        await session.execute(
            select(Briefing)
            .where(Briefing.date <= local_today)
            .order_by(Briefing.date.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    plan = await session.get(Plan, local_today)
    stored = list(briefing.items or [])[:MAX_ITEMS] if briefing is not None else []
    items = [item for raw in stored if (item := today_item(raw)) is not None]
    lines = [line for line in (plan.lines if plan is not None else []) if isinstance(line, str)]
    return TodayResponse(
        date=briefing.date if briefing is not None else local_today,
        items=items,
        plan_lines=lines[:MAX_PLAN_LINES],
    )
