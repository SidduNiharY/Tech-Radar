"""Feedback buttons, signals, the action log and the owner-only callback (Phase 11 Task 2)."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import func, select

from techradar.bot.callbacks import handle_callback_query
from techradar.briefing.compose import StoryCandidate, story_feedback_rows
from techradar.db.models import ActionLog, Answer, Briefing, Feedback
from techradar.feedback.actions import follow_up_class, infer_skips, log_action, note_ask
from techradar.feedback.signals import (
    BUTTONS,
    TARGET_CODES,
    Signal,
    TargetKind,
    feedback_buttons,
    parse_feedback_callback,
    record_feedback,
)
from techradar.schemas.pipeline import Section

NOW = datetime(2026, 11, 15, 12, 0, 0, tzinfo=UTC)
PATTERN = r"^[a-z_]{1,20}(:[0-9]{1,12}){1,2}$"


def test_buttons_match_callback_pattern():
    for kind in BUTTONS:
        for row in feedback_buttons(kind, 123456):
            assert all(re.fullmatch(PATTERN, b.data) for b in row)


def test_every_plan_button_exists():
    labels = {b.text for kind in BUTTONS for row in feedback_buttons(kind, 1) for b in row}
    assert {"👍", "👎", "Wrong source", "More like this", "Off syllabus", "Not a mistake"} <= labels


def test_parse_feedback_callback_round_trip_and_rejects():
    for kind, sigs in BUTTONS.items():
        for sig in sigs:
            assert parse_feedback_callback(f"fb_{sig.value}", [TARGET_CODES[kind], 9]) == (
                kind,
                sig,
                9,
            )
    assert parse_feedback_callback("fb_up", [TARGET_CODES[TargetKind.CARD], 9]) is None  # no 👍
    assert parse_feedback_callback("fb_nope", [1, 9]) is None
    assert parse_feedback_callback("fb_up", [99, 9]) is None
    assert parse_feedback_callback("fb_up", [1]) is None
    assert parse_feedback_callback("ans", [1, 2]) is None


async def test_group_member_feedback_ignored_before_any_data_access():
    # the owner check comes first: a session of None would raise if it were touched
    r = await record_feedback(
        None,  # type: ignore[arg-type]
        kind=TargetKind.MCQ,
        target_id=1,
        signal=Signal.TOO_EASY,
        actor="telegram",
        chat_id=-100,
        owner_id=42,
        now=NOW,
    )
    assert r == "ignored"


def test_follow_up_class_uses_the_owners_words():
    assert follow_up_class("give me an example") == "follow:example"
    assert follow_up_class("make it simpler") == "follow:simpler"
    assert follow_up_class("why is that") == "follow:why"
    assert follow_up_class("thanks") == "follow:other"


def test_story_feedback_rows_one_row_per_story_shown():
    a = StoryCandidate(cluster_id="11", title="First story here", section=Section.TECH)
    b = StoryCandidate(cluster_id="22", title="Other", section=Section.TECH)
    rows = story_feedback_rows("TECH\n• First story here ✅\n  Why: x", [a, b])
    assert len(rows) == 1
    assert [x.data for x in rows[0]] == [
        f"fb_up:{TARGET_CODES[TargetKind.DIGEST_ITEM]}:11",
        f"fb_down:{TARGET_CODES[TargetKind.DIGEST_ITEM]}:11",
        f"fb_not_relevant:{TARGET_CODES[TargetKind.DIGEST_ITEM]}:11",
        f"fb_more_like_this:{TARGET_CODES[TargetKind.DIGEST_ITEM]}:11",
    ]


class FakeQuery:
    def __init__(self, data: str, from_id: int, chat_id: int | None) -> None:
        self.data = data
        self.from_user = SimpleNamespace(id=from_id)
        self.message = (
            None if chat_id is None else SimpleNamespace(chat=SimpleNamespace(id=chat_id))
        )
        self.answers: list[str | None] = []

    async def answer(self, text: str | None = None) -> None:
        self.answers.append(text)


def _update(query: FakeQuery) -> Any:
    return SimpleNamespace(callback_query=query)


def _context(owner: int, factory: Any = None) -> Any:
    bot_data: dict[str, Any] = {"owner_id": owner}
    if factory is not None:
        bot_data["session_factory"] = factory
    return SimpleNamespace(application=SimpleNamespace(bot_data=bot_data))


class ExplodingFactory:
    def __call__(self) -> Any:
        raise AssertionError("a foreign tap must not open a session")


@pytest.mark.parametrize(
    ("from_id", "chat_id"),
    [(7, 42), (42, -100), (42, None)],  # a stranger; the owner's tap in a group; no message
)
async def test_feedback_callback_ignored_outside_the_owners_own_chat(from_id, chat_id):
    q = FakeQuery(f"fb_down:{TARGET_CODES[TargetKind.ANSWER]}:5", from_id, chat_id)
    await handle_callback_query(_update(q), _context(42, ExplodingFactory()))
    assert q.answers in ([None], ["Not available."])


@pytest.mark.db
async def test_group_member_feedback_ignored(session):
    r = await record_feedback(
        session,
        kind=TargetKind.MCQ,
        target_id=1,
        signal=Signal.TOO_EASY,
        actor="telegram",
        chat_id=-100,
        owner_id=42,
        now=NOW,
    )
    assert r == "ignored"
    assert (await session.execute(select(func.count()).select_from(Feedback))).scalar() == 0


@pytest.mark.db
async def test_duplicate_feedback_counted_once(session):
    results = [
        await record_feedback(
            session,
            kind=TargetKind.ANSWER,
            target_id=7,
            signal=Signal.DOWN,
            actor="telegram",
            chat_id=42,
            owner_id=42,
            now=NOW,
        )
        for _ in range(10)
    ]
    assert results[0] == "recorded" and set(results[1:]) == {"duplicate"}
    assert (await session.execute(select(func.count()).select_from(Feedback))).scalar() == 1


@pytest.mark.db
async def test_signal_without_a_button_for_the_target_is_ignored(session):
    r = await record_feedback(
        session,
        kind=TargetKind.CARD,
        target_id=1,
        signal=Signal.UP,
        actor="web",
        chat_id=None,
        owner_id=42,
        now=NOW,
    )
    assert r == "ignored"


@pytest.mark.db
async def test_rate_limited_after_120(session):
    results = [
        await record_feedback(
            session,
            kind=TargetKind.ANSWER,
            target_id=1000 + i,
            signal=Signal.UP,
            actor="web",
            chat_id=None,
            owner_id=42,
            now=NOW,
        )
        for i in range(121)
    ]
    assert results[:120] == ["recorded"] * 120 and results[120] == "rate_limited"


@pytest.mark.db
async def test_follow_up_logged_within_ten_minutes(session):
    session.add(Answer(chat_id=42, question="What is CRR?", text="t", status="answered"))
    await session.flush()
    await note_ask(
        session, chat_id=42, question="give me an example", mode="gate", now=datetime.now(UTC)
    )
    rows = (
        (await session.execute(select(ActionLog).where(ActionLog.kind == "follow_up")))
        .scalars()
        .all()
    )
    assert (
        len(rows) == 1
        and rows[0].target.startswith("answer:")
        and rows[0].topic == "follow:example"
    )
    # an ask long after the answer is only an `ask`
    await note_ask(
        session, chat_id=42, question="x", mode=None, now=datetime.now(UTC) + timedelta(minutes=30)
    )
    rows = (
        (await session.execute(select(ActionLog).where(ActionLog.kind == "follow_up")))
        .scalars()
        .all()
    )
    assert len(rows) == 1


@pytest.mark.db
async def test_infer_skips_only_for_untouched_stories(session):
    day = date(2026, 11, 14)
    session.add(
        Briefing(
            date=day,
            sent_at=NOW - timedelta(days=2),
            items=[
                {
                    "cluster_id": "1",
                    "topic_keys": ["section:tech"],
                    "source_keys": ["source:a.com"],
                },
                {"cluster_id": "2", "topic_keys": ["section:tech"], "source_keys": []},
                {"cluster_id": "3", "topic_keys": [], "source_keys": []},
            ],
        )
    )
    await log_action(session, "open", "story:2", now=NOW - timedelta(days=2))
    session.add(
        Feedback(
            target_kind="digest_item",
            target_id=3,
            signal="up",
            actor="telegram",
            day=day,
            at=NOW - timedelta(days=2, hours=-1),
        )
    )
    await session.flush()
    assert await infer_skips(session, day) == 1
    assert await infer_skips(session, day) == 0  # judged once
    skips = (
        (await session.execute(select(ActionLog).where(ActionLog.kind == "skip"))).scalars().all()
    )
    assert [s.target for s in skips] == ["story:1"]
