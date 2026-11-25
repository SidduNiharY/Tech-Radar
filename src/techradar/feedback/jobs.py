"""Bodies of the Phase 11 jobs. The tasks in worker/tasks.py only build the dependencies."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.feedback.actions import infer_skips
from techradar.feedback.patterns import run_find_patterns
from techradar.planner.sessions import local_date


class NightlyResult(BaseModel):
    skips_inferred: int = 0
    candidates: int = 0


async def run_nightly_patterns(
    session: AsyncSession, embedder: Any, *, now: datetime, owner_chat_id: int
) -> NightlyResult:
    """Nightly, plain code: turn yesterday's untouched stories into skips, then find patterns.

    Finding patterns only counts rows. Its one automatic change is lowering a source with 5 bad
    signals, which is bounded and logged. No model is called here (SEC-48).
    """
    yesterday = local_date(now - timedelta(days=1))
    skips = await infer_skips(session, yesterday)
    found = await run_find_patterns(session, embedder, now, owner_chat_id=owner_chat_id)
    return NightlyResult(skips_inferred=skips, candidates=len(found))
