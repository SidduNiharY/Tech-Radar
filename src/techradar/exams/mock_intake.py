"""Mock scorecards read by the parser sandbox, stored and answered (Phase 8 Task 5).

The bot queued each scorecard as a `purpose="mock"` parse job (bot/mock_intake.py). Here
the worker takes each `mock` result:
- only an `ok` result with the verdict `pass` is used; a flagged, rejected or empty one
  asks the owner to type the scores instead;
- `extract_mock` reads the OCR text by regex first; the worker model is a fallback whose
  numbers must all appear in the OCR text (no invented scores);
- the scores go to `mock_results` and the reply compares them with the latest cutoff of
  the owner's category.

Result files are read without following a link and with a size cap (the parser can write
the clean folder). The row and the reply are committed before the result is removed.

SEC: SEC-06, SEC-17, SEC-18.
"""

from __future__ import annotations

import contextlib
import logging
import os
from collections.abc import Awaitable, Callable
from datetime import date
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import Cutoff, MockResult
from techradar.exams.mocks import MockScore, extract_mock, render_mock_reply
from techradar.exams.pyq_intake import MAX_RESULT_BYTES, read_nofollow
from techradar.llm.client import Completer
from techradar.schemas.pipeline import ParseResult

log = logging.getLogger(__name__)

MAX_MOCKS_PER_RUN = 5  # each may need one model call
FAILED = (
    "I couldn't read that scorecard reliably. Please type the scores: "
    "/mock <section>=<score>/<max> …"
)
_SUFFIX = ".result.json"

Send = Callable[[str], Awaitable[None]]


def _mock_results(clean_dir: Path, limit: int) -> list[ParseResult]:
    found: list[ParseResult] = []
    try:
        names = sorted(e.name for e in os.scandir(clean_dir) if e.name.endswith(_SUFFIX))
    except OSError:
        return found
    for name in names:
        data = read_nofollow(clean_dir, name, MAX_RESULT_BYTES)
        if data is None:
            continue
        try:
            result = ParseResult.model_validate_json(data)
        except ValidationError:
            continue
        if result.purpose != "mock" or name != f"{result.job_id}{_SUFFIX}":
            continue
        found.append(result)
        if len(found) >= limit:
            break
    return found


def usable_text(result: ParseResult) -> str | None:
    """The OCR text when the gateway passed it unflagged, else None."""
    if result.status != "ok" or result.doc is None:
        return None
    if result.intake is None or result.intake.verdict != "pass":
        return None
    return result.doc.text


async def latest_cutoff(session: AsyncSession, exam: str, category: str) -> float | None:
    row = (
        await session.execute(
            select(Cutoff.score)
            .where(Cutoff.exam == exam, Cutoff.category == category)
            .order_by(Cutoff.year.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return float(row) if row is not None else None


async def store_mock(session: AsyncSession, m: MockScore, *, today: date, category: str) -> str:
    """Save the scores and return the reply for the owner."""
    session.add(
        MockResult(
            exam=m.exam,
            taken_on=today,
            total=m.total,
            max_total=m.max_total,
            sections=[s.model_dump() for s in m.sections],
            source="screenshot",
        )
    )
    await session.flush()
    return render_mock_reply(m, await latest_cutoff(session, m.exam, category), category)


async def collect_mock_results(
    session: AsyncSession,
    clean_dir: Path,
    completer: Completer,
    *,
    today: date,
    category: str,
    send: Send,
    max_results: int = MAX_MOCKS_PER_RUN,
) -> int:
    """Answer every `mock` result in the clean folder; returns how many were handled."""
    handled = 0
    for result in _mock_results(clean_dir, max_results):
        try:
            text = usable_text(result)
            m = await extract_mock(completer, text) if text is not None else None
            reply = await store_mock(session, m, today=today, category=category) if m else FAILED
            await send(reply)
            await session.commit()
        except Exception:
            log.exception("mock result %s failed", result.job_id)
            await session.rollback()
            continue
        with contextlib.suppress(OSError):
            (clean_dir / f"{result.job_id}{_SUFFIX}").unlink()
        handled += 1
    return handled
