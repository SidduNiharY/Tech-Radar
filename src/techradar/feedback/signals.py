"""Feedback signals, target types, button builders, and recording logic."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import Feedback
from techradar.feedback.weights import STEP
from techradar.messaging.outbox import Button

FeedbackResult = Literal["recorded", "duplicate", "ignored", "rate_limited"]
RATE_LIMIT_PER_HOUR = 120


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
    """Record one piece of the owner's feedback (SEC-26, SEC-49).

    ignored: a Telegram tap from any chat but the owner's, or a signal the target has no button
    for. duplicate: the same target, signal and day again. rate_limited: 120 events in an hour.
    The owner check comes first and touches no data.
    """
    if actor == "telegram" and chat_id != owner_id:
        return "ignored"
    if signal not in BUTTONS.get(kind, []):
        return "ignored"

    hour_ago = now - timedelta(hours=1)
    cnt = (
        await session.execute(
            select(func.count()).select_from(Feedback).where(Feedback.at >= hour_ago)
        )
    ).scalar() or 0
    if cnt >= RATE_LIMIT_PER_HOUR:
        return "rate_limited"

    row = Feedback(
        target_kind=kind.value,
        target_id=target_id,
        signal=signal.value,
        actor=actor,
        day=now.date(),
        at=now,
    )
    try:
        async with session.begin_nested():  # the unique index decides, even for racing taps
            session.add(row)
            await session.flush()
    except IntegrityError:
        return "duplicate"

    if kind is TargetKind.DIGEST_ITEM and signal.value in STEP:
        from techradar.feedback.weights import apply_digest_signal

        await apply_digest_signal(session, target_id, STEP[signal.value], now)
    return "recorded"


_CODE_TO_KIND = {code: kind for kind, code in TARGET_CODES.items()}


def parse_feedback_callback(
    action: str, args: Sequence[int]
) -> tuple[TargetKind, Signal, int] | None:
    """`fb_<signal>:<code>:<target id>` to (kind, signal, id); None for anything else."""
    if not action.startswith("fb_") or len(args) != 2:
        return None
    try:
        signal = Signal(action[3:])
    except ValueError:
        return None
    kind = _CODE_TO_KIND.get(args[0])
    if kind is None or signal not in BUTTONS[kind] or args[1] < 0:
        return None
    return kind, signal, args[1]
