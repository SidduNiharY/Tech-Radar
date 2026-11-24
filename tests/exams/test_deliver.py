from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import DrillAttempt
from techradar.exams.deliver import (
    DrillOutcome,
    day_attempts,
    drill_day,
    next_unanswered,
    record_drill,
    render_drill_feedback,
    render_drill_item,
    render_drill_summary,
)
from techradar.exams.drills import daily_set


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


def test_drill_day_is_the_local_day():
    sent = datetime(2026, 11, 21, 19, 0, tzinfo=UTC)
    assert drill_day(sent, "Asia/Kolkata") == date(2026, 11, 22)
    assert drill_day(sent, "UTC") == date(2026, 11, 21)


def test_render_drill_item_never_shows_the_key():
    item = daily_set(date(2026, 11, 8))[0]
    text, buttons = render_drill_item(item, 0)
    assert text.startswith("Drill 1/20") and item.question in text
    assert [b.data for b in buttons[0]] == [f"drill:0:{i}" for i in range(4)]
    assert item.explanation not in text


def test_render_drill_feedback():
    ok = DrillOutcome(correct=True, explanation="e", seconds=41.0, chosen="4", answer_option="4")
    bad = DrillOutcome(correct=False, explanation="why", seconds=3.0, chosen="5", answer_option="4")
    assert render_drill_feedback(ok) == "✅ Correct · 41 s"
    assert render_drill_feedback(bad) == "❌ Not quite. Answer: 4\nwhy"


def test_exam_drills_never_use_a_model():
    """Every key is computed in code: the drill modules import no model client."""
    import ast
    from pathlib import Path

    files = [Path("src/techradar/exams/deliver.py"), Path("src/techradar/bot/drill.py")]
    files += sorted(Path("src/techradar/exams/drills").glob("*.py"))
    for f in files:
        for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            mod = (
                node.module
                if isinstance(node, ast.ImportFrom)
                else ".".join(a.name for a in node.names)
                if isinstance(node, ast.Import)
                else ""
            )
            assert "techradar.llm" not in (mod or ""), f


@pytest.mark.db
async def test_next_unanswered_resumes_where_the_owner_stopped(session: AsyncSession):
    day = date(2026, 11, 8)
    assert await next_unanswered(session, day) == 0
    t = datetime(2026, 11, 8, 10, 0, tzinfo=UTC)
    for n in (0, 1):
        await record_drill(session, day, n, 0, t, t)
    assert await next_unanswered(session, day) == 2
    assert len(await day_attempts(session, day)) == 2


@pytest.mark.db
async def test_record_drill_rejects_a_choice_that_is_not_an_option(session: AsyncSession):
    t = datetime(2026, 11, 8, 10, 0, tzinfo=UTC)
    with pytest.raises(ValueError):
        await record_drill(session, date(2026, 11, 8), 0, 7, t, t)


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
