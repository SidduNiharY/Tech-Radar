"""Morning greeting (Phase 12 Task 9)."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import (
    Briefing,
    Flashcard,
    JarvisGreeting,
    Revision,
    SyllabusTopic,
    TopicMastery,
    TopicSource,
    UserSettings,
)
from techradar.jarvis.greeting import (
    Greeting,
    Suggestion,
    choose_suggestions,
    is_quiet_hours,
    outside_usual_day,
    render_greeting,
    run_prepare_greeting,
)

QUIET = (time(23, 0), time(6, 0))
NOW = datetime(2026, 11, 25, 7, 30, tzinfo=UTC)  # 2026-11-25 is not an outside-usual day
KINDS = ["news", "due_cards", "revision", "weak_topic", "no_source", "outside_usual"]


def sug(kind: str, text: str | None = None) -> Suggestion:
    return Suggestion(kind=kind, text=text or f"{kind} text")  # type: ignore[arg-type]


def test_at_most_three_suggestions():
    assert len(choose_suggestions([sug(k) for k in KINDS * 2])) == 3


def test_priority_order():
    shuffled = [sug(k) for k in ("no_source", "weak_topic", "news", "due_cards", "revision")]
    assert [s.kind for s in choose_suggestions(shuffled)] == ["news", "due_cards", "revision"]


def test_outside_usual_only_on_its_days():
    cands = [sug(k) for k in KINDS]
    assert "outside_usual" not in [s.kind for s in choose_suggestions(cands)]
    picked = choose_suggestions(cands, include_outside_usual=True)
    assert len(picked) == 3 and picked[-1].kind == "outside_usual"
    assert [s.kind for s in picked[:2]] == ["news", "due_cards"]


def test_outside_usual_appears_once_in_ten():
    start = date(2026, 11, 1)
    days = [start + timedelta(days=i) for i in range(10)]
    assert sum(outside_usual_day(d) for d in days) == 1


def test_render_greeting_counts():
    two = Greeting(opening="Good morning.", suggestions=[sug("news", "A."), sug("due_cards", "B.")])
    assert render_greeting(two).startswith("Good morning. Two things today:\n1. A.\n2. B.")
    assert render_greeting(two).endswith("What do you want to start with?")
    one = Greeting(opening="Good morning.", suggestions=[sug("news", "A.")])
    assert "One thing today:" in render_greeting(one)
    assert "Three things" in render_greeting(
        Greeting(opening="Hi.", suggestions=[sug("news"), sug("revision"), sug("weak_topic")])
    )
    assert "Nothing urgent" in render_greeting(Greeting(opening="Hi."))


def test_suggestion_text_has_no_links_and_a_length_cap():
    with pytest.raises(ValidationError):
        Suggestion(kind="news", text="see https://evil.example now")
    with pytest.raises(ValidationError):
        Suggestion(kind="news", text="x" * 161)
    with pytest.raises(ValidationError):
        Greeting(opening="Hi.", suggestions=[sug("news")] * 4)


def test_quiet_hours_cross_midnight():
    def at(h: int, m: int = 0) -> datetime:
        return datetime(2026, 11, 25, h, m, tzinfo=UTC)

    assert is_quiet_hours(at(23), QUIET) and is_quiet_hours(at(2), QUIET)
    assert is_quiet_hours(at(5, 59), QUIET)
    assert not is_quiet_hours(at(6), QUIET) and not is_quiet_hours(at(22, 59), QUIET)
    assert is_quiet_hours(at(13, 30), (time(13), time(15)))
    assert not is_quiet_hours(at(15), (time(13), time(15)))


# --- database -------------------------------------------------------------------------------

db = pytest.mark.db


async def _briefing(session: AsyncSession, items: list[dict] | None = None) -> None:
    session.add(Briefing(date=NOW.date(), sent_at=NOW, items=items or []))
    await session.flush()


@db
async def test_greeting_stored_once_from_real_rows(session: AsyncSession):
    await _briefing(
        session,
        [
            {"title": "RBI", "section": "economy", "exam_tags": ["bank"]},
            {"title": "Chips", "section": "tech", "exam_tags": []},
        ],
    )
    session.add(Flashcard(front="f", back="b", source_kind="fact", due=NOW - timedelta(hours=1)))
    session.add(Revision(goal="gov", topic="polity", due_date=NOW.date()))
    session.add(TopicMastery(topic="OS", level="learning", prev_level="exam_ready"))
    await session.flush()

    g = await run_prepare_greeting(session, NOW)
    assert g is not None and g.opening == "Good morning."
    assert [s.kind for s in g.suggestions] == ["news", "due_cards", "revision"]
    row = await session.get(JarvisGreeting, NOW.date())
    assert row is not None and row.shown_devices == []
    assert row.greeting["suggestions"][0]["kind"] == "news"
    # A second run changes nothing.
    assert await run_prepare_greeting(session, NOW) is None
    assert len((await session.execute(select(JarvisGreeting))).scalars().all()) == 1


@db
async def test_no_greeting_before_the_briefing(session: AsyncSession):
    assert await run_prepare_greeting(session, NOW) is None
    assert await session.get(JarvisGreeting, NOW.date()) is None


@db
async def test_no_greeting_in_quiet_hours_and_the_setting_is_used(session: AsyncSession):
    await _briefing(session)
    late = NOW.replace(hour=23, minute=30)
    assert await run_prepare_greeting(session, late) is None
    assert await run_prepare_greeting(session, NOW.replace(hour=2)) is None
    session.add(UserSettings(key="jarvis_quiet_hours", value="07:00-08:00"))
    await session.flush()
    assert await run_prepare_greeting(session, NOW) is None  # 07:30 is now quiet
    assert await run_prepare_greeting(session, NOW.replace(hour=9)) is not None


@db
async def test_no_source_suggestion_only_with_a_suggested_source(session: AsyncSession):
    await _briefing(session)
    topic = SyllabusTopic(
        exam="gate", subject="OS", topic="Banker's algorithm", slug="bankers", vault_path="v"
    )
    session.add(topic)
    await session.flush()
    g = await run_prepare_greeting(session, NOW)
    assert g is not None and g.suggestions == []
    await session.execute(
        JarvisGreeting.__table__.delete().where(JarvisGreeting.date == NOW.date())
    )
    session.add(
        TopicSource(
            topic_id=topic.id, kind="chapter", ref_id=1, label="NPTEL OS week 5", status="suggested"
        )
    )
    await session.flush()
    g2 = await run_prepare_greeting(session, NOW)
    assert g2 is not None and len(g2.suggestions) == 1
    assert g2.suggestions[0].text == "Banker's algorithm has no material yet. Add NPTEL OS week 5?"


@db
async def test_outside_usual_story_on_its_day(session: AsyncSession):
    day = next(
        NOW.date() + timedelta(days=i)
        for i in range(10)
        if outside_usual_day(NOW.date() + timedelta(days=i))
    )
    now = datetime.combine(day, time(7, 30), tzinfo=UTC)
    session.add(Briefing(date=day, sent_at=now, items=[{"title": "t", "section": "science"}]))
    session.add(Flashcard(front="f", back="b", source_kind="fact", due=now - timedelta(hours=1)))
    await session.flush()
    g = await run_prepare_greeting(session, now)
    assert g is not None and [s.kind for s in g.suggestions] == ["due_cards", "outside_usual"]
