from __future__ import annotations

from datetime import date

import pytest

from techradar.briefing.compose import Briefing, render_briefing
from techradar.planner.plan import RevisionRow, compose_plan, plan_for_today
from techradar.planner.sessions import Goal

TODAY = date(2026, 11, 15)
TARGETS = {
    Goal.DEV: 600,
    Goal.GATE: 300,
    Goal.GOV: 420,
    Goal.CURRENT: 105,
    Goal.ENGLISH: 140,
}
REV_GATE_OS = RevisionRow(Goal.GATE, "os")


def test_plan_orders_and_picks_most_behind_goal():
    lines = compose_plan(
        TODAY,
        due_revisions=[REV_GATE_OS],
        due_cards=18,
        quiz_ready=True,
        minutes_this_week={Goal.GATE: 30, Goal.GOV: 400},
        targets=TARGETS,
        priority=[Goal.GOV, Goal.GATE],
    )
    assert lines == [
        "📰 Radar (10–15 min)",
        "📝 Current affairs quiz: 10 MCQs",
        "🔁 Reviews due: 18 flashcards + 1 topic revisions",
        "🎓 GATE: os (45 min)",
        "🔤 English: 5 new words + 10 grammar questions",
    ]


def test_plan_final_30_first_line():
    lines = compose_plan(
        TODAY,
        due_revisions=[],
        due_cards=0,
        quiz_ready=False,
        minutes_this_week={},
        targets=TARGETS,
        priority=[Goal.GOV],
        final_30_exam="SSC CGL",
    )
    assert lines[0] == "⏳ Final 30 days: SSC CGL"


def test_plan_in_final_mode_never_suggests_new_topic():
    lines = compose_plan(
        TODAY,
        due_revisions=[],
        due_cards=0,
        quiz_ready=False,
        minutes_this_week={},
        targets=TARGETS,
        priority=[Goal.GOV],
        final_30_exam="SSC CGL",
    )
    assert not any("next topic" in line for line in lines)
    assert any("revise" in line for line in lines)


def test_briefing_shows_plan_block_first():
    b = Briefing(
        date=TODAY,
        sent_at=TODAY,
        items=[],
        plan_lines=["Line 1", "Line 2"],
    )
    msgs = render_briefing(b)
    assert len(msgs) > 0
    assert "TODAY'S PLAN\nLine 1\nLine 2" in msgs[0]


def test_plan_tie_broken_by_priority_and_names_no_topic_when_none_due():
    lines = compose_plan(
        TODAY,
        due_revisions=[],
        due_cards=0,
        quiz_ready=False,
        minutes_this_week={},
        targets=TARGETS,
        priority=[Goal.GOV, Goal.GATE],
    )
    assert lines == [
        "📰 Radar (10–15 min)",
        "🎓 GOV: next topic (45 min)",
        "🔤 English: 5 new words + 10 grammar questions",
    ]


def test_user_settings_plan_defaults():
    from techradar.api.schemas import UserSettings

    s = UserSettings(briefing_time="06:30", sections=["tech"])
    assert s.exam_priority == [Goal.GOV, Goal.GATE]
    assert s.exam_dates == {}
    assert s.weekly_targets_min == {
        Goal.DEV: 600,
        Goal.GATE: 300,
        Goal.GOV: 420,
        Goal.CURRENT: 105,
        Goal.ENGLISH: 140,
    }


@pytest.mark.db
@pytest.mark.asyncio
async def test_revisions_due_in_a_30_hour_gap_appear_in_the_next_plan(session):
    from datetime import UTC, datetime

    from sqlalchemy import select

    from techradar.db.models import Plan, Revision

    session.add(Revision(goal="gate", topic="os", due_date=date(2026, 11, 14)))
    session.add(Revision(goal="gate", topic="dbms", due_date=date(2026, 11, 15)))
    session.add(Revision(goal="gate", topic="later", due_date=date(2026, 11, 20)))
    await session.flush()
    now = datetime(2026, 11, 15, 1, 0, tzinfo=UTC)  # 06:30 in India
    lines = await plan_for_today(session, now)
    assert "🔁 Reviews due: 2 topic revisions" in lines
    again = await plan_for_today(session, now)  # idempotent: one stored row per day
    assert again == lines
    rows = (await session.execute(select(Plan).where(Plan.date == date(2026, 11, 15)))).scalars()
    assert [p.lines for p in rows] == [lines]
