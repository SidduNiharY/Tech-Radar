"""Feedback signals, target types, button builders, and recording logic."""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import StrEnum
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import Feedback
from techradar.messaging.outbox import Button

FeedbackResult = Literal["recorded", "duplicate", "ignored", "rate_limited"]


class Signal(StrEnum):
    """Signals for user feedback buttons."""

    UP = "up"
    DOWN = "down"
    WRONG = "wrong"
    WRONG_SOURCE = "wrong_source"
    TOO_LONG = "too_long"
    TOO_SHALLOW = "too_shallow"
    NOT_RELEVANT = "not_relevant"
    MORE_LIKE_THIS = "more_like_this"
    TOO_EASY = "too_easy"
    TOO_HARD = "too_hard"
    OFF_SYLLABUS = "off_syllabus"
    BAD_CARD = "bad_card"
    WRONG_KEY = "wrong_key"
    NOT_A_MISTAKE = "not_a_mistake"
    SIMPLER = "simpler"
    GIVE_EXAMPLE = "give_example"


class TargetKind(StrEnum):
    """Kinds of targets that receive feedback."""

    DIGEST_ITEM = "digest_item"
    ANSWER = "answer"
    SUMMARY = "summary"
    CHAPTER_SUMMARY = "chapter_summary"
    CARD = "card"
    MCQ = "mcq"
    VOICE = "voice"


TARGET_CODES: dict[TargetKind, int] = {
    TargetKind.DIGEST_ITEM: 1,
    TargetKind.ANSWER: 2,
    TargetKind.SUMMARY: 3,
    TargetKind.CHAPTER_SUMMARY: 4,
    TargetKind.CARD: 5,
    TargetKind.MCQ: 6,
    TargetKind.VOICE: 7,
}

BUTTONS: dict[TargetKind, list[Signal]] = {
    TargetKind.DIGEST_ITEM: [
        Signal.UP,
        Signal.DOWN,
        Signal.NOT_RELEVANT,
        Signal.MORE_LIKE_THIS,
    ],
    TargetKind.ANSWER: [
        Signal.UP,
        Signal.DOWN,
        Signal.WRONG,
        Signal.WRONG_SOURCE,
        Signal.TOO_LONG,
    ],
    TargetKind.SUMMARY: [
        Signal.UP,
        Signal.DOWN,
        Signal.TOO_LONG,
        Signal.TOO_SHALLOW,
    ],
    TargetKind.CHAPTER_SUMMARY: [
        Signal.UP,
        Signal.DOWN,
        Signal.TOO_LONG,
        Signal.TOO_SHALLOW,
    ],
    TargetKind.CARD: [
        Signal.WRONG,
        Signal.BAD_CARD,
    ],
    TargetKind.MCQ: [
        Signal.WRONG_KEY,
        Signal.TOO_EASY,
        Signal.TOO_HARD,
        Signal.OFF_SYLLABUS,
    ],
    TargetKind.VOICE: [
        Signal.UP,
        Signal.DOWN,
        Signal.NOT_A_MISTAKE,
    ],
}

SIGNAL_LABELS: dict[Signal, str] = {
    Signal.UP: "👍",
    Signal.DOWN: "👎",
    Signal.WRONG: "Wrong",
    Signal.WRONG_SOURCE: "Wrong source",
    Signal.TOO_LONG: "Too long",
    Signal.TOO_SHALLOW: "Too shallow",
    Signal.NOT_RELEVANT: "Not relevant",
    Signal.MORE_LIKE_THIS: "More like this",
    Signal.TOO_EASY: "Too easy",
    Signal.TOO_HARD: "Too hard",
    Signal.OFF_SYLLABUS: "Off syllabus",
    Signal.BAD_CARD: "Bad card",
    Signal.WRONG_KEY: "Wrong key",
    Signal.NOT_A_MISTAKE: "Not a mistake",
    Signal.SIMPLER: "Simpler",
    Signal.GIVE_EXAMPLE: "Give example",
}


def feedback_buttons(kind: TargetKind, target_id: int) -> list[list[Button]]:
    """Build inline keyboard buttons for user feedback on a target."""
    signals = BUTTONS.get(kind, [])
    code = TARGET_CODES[kind]
    buttons = [
        Button(
            text=SIGNAL_LABELS[sig],
            data=f"fb_{sig.value}:{code}:{target_id}",
        )
        for sig in signals
    ]
    if len(buttons) >= 2 and signals[0] == Signal.UP and signals[1] == Signal.DOWN:
        rows = [buttons[:2]]
        rest = buttons[2:]
        for i in range(0, len(rest), 2):
            rows.append(rest[i : i + 2])
        return rows
    rows = []
    for i in range(0, len(buttons), 2):
        rows.append(buttons[i : i + 2])
    return rows


async def record_feedback(
    session: AsyncSession,
    *,
    kind: TargetKind,
    target_id: int,
    signal: Signal,
    actor: Literal["telegram", "web", "voice"],
    chat_id: int | None,
    owner_id: int,
    now: datetime,
) -> FeedbackResult:
    """Record user feedback under owner-only and rate-limiting constraints."""
    if actor == "telegram" and chat_id != owner_id:
        return "ignored"

    # Rate limiting: at most 120 feedback events in the last hour
    hour_ago = now - timedelta(hours=1)
    rate_stmt = select(func.count()).select_from(Feedback).where(Feedback.at >= hour_ago)
    cnt = (await session.execute(rate_stmt)).scalar() or 0
    if cnt >= 120:
        return "rate_limited"

    # Duplicate check: same target, signal and day
    today = now.date()
    dup_stmt = select(Feedback).where(
        Feedback.target_kind == kind.value,
        Feedback.target_id == target_id,
        Feedback.signal == signal.value,
        Feedback.day == today,
    )
    existing = (await session.execute(dup_stmt)).scalar_one_or_none()
    if existing is not None:
        return "duplicate"

    row = Feedback(
        target_kind=kind.value,
        target_id=target_id,
        signal=signal.value,
        actor=actor,
        day=today,
        at=now,
    )
    session.add(row)
    await session.flush()

    # Apply weight adjustment if signal is weight-bearing
    from techradar.feedback.weights import STEP, apply_signal

    if signal.value in STEP:
        delta = STEP[signal.value]
        # In basic mode, we pass target as a topic key if target_kind is digest/topic
        topic_key = f"target:{kind.value}:{target_id}"
        await apply_signal(
            session,
            topics=[topic_key],
            source=None,
            delta=delta,
            exam_topic=False,
            now=now,
        )

    return "recorded"
