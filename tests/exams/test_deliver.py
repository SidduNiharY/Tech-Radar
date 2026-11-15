from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from techradar.db.engine import make_engine
from techradar.db.models import DrillAttempt
from techradar.exams.deliver import record_drill, render_drill_summary
from techradar.exams.drills import daily_set
from techradar.settings import Settings


def test_daily_set_is_deterministic():
    d = date(2026, 11, 8)
    assert [i.question for i in daily_set(d)] == [i.question for i in daily_set(d)]


def test_render_drill_summary():
    attempts = [
        DrillAttempt(
            day=date(2026, 11, 8),
            kind="quant_simple_interest",
            item={},
            chosen="100",
            correct=True,
            seconds=12.0,
        ),
        DrillAttempt(
            day=date(2026, 11, 8),
            kind="quant_compound_interest",
            item={},
            chosen="120",
            correct=False,
            seconds=40.0,
        ),
    ]
    summary = render_drill_summary(attempts)
    assert summary == "Aptitude: 1/2 · avg 26.0 s per question · slowest: quant_compound_interest"


def test_render_drill_summary_empty():
    assert render_drill_summary([]) == "Aptitude: 0/0 · avg 0.0 s per question · slowest: none"


@pytest.fixture
def db_settings() -> Settings:
    return Settings(
        telegram_owner_chat_id=1,
        db_host="127.0.0.1",
        db_port=55432,
        db_name="techradar",
        secrets_dir=Path("secrets"),
    )


@pytest.fixture
async def session(db_settings: Settings) -> AsyncGenerator[AsyncSession]:
    engine = make_engine("app", db_settings)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s
        await s.rollback()
    await engine.dispose()


@pytest.mark.db
async def test_record_drill_idempotent_and_timed(session: AsyncSession):
    day = date(2026, 11, 8)
    items = daily_set(day)
    q0 = items[0]

    sent_at = datetime(2026, 11, 8, 10, 0, 0, tzinfo=UTC)
    now = sent_at + timedelta(seconds=41.0)

    # First attempt: correct choice
    outcome1 = await record_drill(session, day, 0, q0.answer_index, sent_at, now)
    assert not outcome1.already_answered
    assert outcome1.correct is True
    assert outcome1.seconds == 41.0

    # Second tap: different choice ignored, returns previous outcome
    wrong_idx = (q0.answer_index + 1) % len(q0.options)
    now2 = now + timedelta(seconds=10.0)
    outcome2 = await record_drill(session, day, 0, wrong_idx, sent_at, now2)
    assert outcome2.already_answered is True
    assert outcome2.correct is True
    assert outcome2.seconds == 41.0
