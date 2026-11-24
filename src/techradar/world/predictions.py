"""Opinions and predictions log (Phase 7 Task 6).

The owner records a prediction with a due date; on that day the app asks how it went (one tap
and an optional reply), and `context/predictions.md` keeps the whole log. All data is in
Postgres. Functions take a session and flush; the caller commits.

SEC: SEC-26.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path, PurePosixPath
from zoneinfo import ZoneInfo

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import Prediction
from techradar.messaging.outbox import Button, enqueue_message
from techradar.pipeline.writer import write_note
from techradar.security.text import sanitize_text

PREDICTION_PURPOSE = "prediction"
MAX_TEXT = 280
MAX_OUTCOME_TEXT = 500
OUTCOMES = {1: "Right", 2: "Wrong", 3: "Partly"}
USAGE = "Use: /predict <your prediction> by YYYY-MM-DD"
PAST_DATE = "Pick a future date."
TOO_LONG = "Keep it under 280 characters."
CONTEXT_PATH = PurePosixPath("context/predictions.md")

_BY = re.compile(r"\s+by\s+(\S+)\s*$", re.IGNORECASE)


def parse_predict(arg: str, today: date) -> tuple[str, date] | str:
    """`<text> by <YYYY-MM-DD>` as (text, due date), or the error text to send back."""
    arg = " ".join(sanitize_text(arg).split())
    m = _BY.search(arg)
    if m is None:
        return TOO_LONG if len(arg) > MAX_TEXT else USAGE
    text = arg[: m.start()].strip()
    if not text:
        return USAGE
    if len(text) > MAX_TEXT:
        return TOO_LONG
    try:
        due = date.fromisoformat(m.group(1))
    except ValueError:
        return USAGE
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", m.group(1)):
        return USAGE
    if due <= today:
        return PAST_DATE
    return text, due


def render_reminder(text: str, created: date) -> str:
    return (
        f"🔮 Your prediction from {created.day} {created:%b}: {text}. "
        "What happened? Reply to this message."
    )


def reminder_buttons(prediction_id: int) -> list[list[Button]]:
    return [
        [
            Button(text=OUTCOMES[1], data=f"pred:{prediction_id}:1"),
            Button(text=OUTCOMES[2], data=f"pred:{prediction_id}:2"),
            Button(text=OUTCOMES[3], data=f"pred:{prediction_id}:3"),
        ]
    ]


async def record_prediction(session: AsyncSession, text: str, due_date: date) -> int:
    """Save a prediction; the caller commits and regenerates the vault page."""
    pred = Prediction(text=text, due_date=due_date)
    session.add(pred)
    await session.flush()
    return int(pred.id)


async def record_outcome(
    session: AsyncSession, prediction_id: int, outcome: int, outcome_text: str | None = None
) -> bool:
    """Record 1 right, 2 wrong or 3 partly. False when unknown, invalid or already answered."""
    if outcome not in OUTCOMES:
        return False
    pred = await session.get(Prediction, prediction_id)
    if pred is None or pred.outcome is not None:
        return False
    pred.outcome = outcome
    if outcome_text:
        pred.outcome_text = _clean(outcome_text)
    await session.flush()
    return True


async def set_outcome_text(session: AsyncSession, prediction_id: int, text: str) -> bool:
    """Add the owner's words to a prediction's outcome (a reply to its reminder)."""
    pred = await session.get(Prediction, prediction_id)
    cleaned = _clean(text)
    if pred is None or not cleaned:
        return False
    pred.outcome_text = cleaned
    await session.flush()
    return True


def _clean(text: str) -> str:
    return " ".join(sanitize_text(text).split())[:MAX_OUTCOME_TEXT]


async def get_due_predictions(session: AsyncSession, today: date) -> list[Prediction]:
    """Predictions due today or earlier that are unanswered and not yet reminded."""
    stmt = (
        select(Prediction)
        .where(
            Prediction.due_date <= today,
            Prediction.outcome.is_(None),
            Prediction.reminded_at.is_(None),
        )
        .order_by(Prediction.due_date, Prediction.id)
    )
    return list((await session.execute(stmt)).scalars().all())


async def run_prediction_reminder(
    session: AsyncSession, *, now: datetime, owner_chat_id: int, tz: str
) -> int:
    """Send one reminder for each due, unanswered, not yet reminded prediction; returns the count.

    A prediction is marked reminded in the same transaction as its message, so it is asked once.
    """
    zone = ZoneInfo(tz)
    today = now.astimezone(zone).date()
    sent = 0
    for pred in await get_due_predictions(session, today):
        created = pred.created_at.astimezone(zone).date() if pred.created_at else today
        await enqueue_message(
            session,
            chat_id=owner_chat_id,
            text=render_reminder(pred.text, created),
            purpose=PREDICTION_PURPOSE,
            buttons=reminder_buttons(pred.id),
            ref_id=pred.id,
        )
        pred.reminded_at = now
        sent += 1
    await session.flush()
    return sent


def render_predictions_context(predictions: list[Prediction], tz: str = "Asia/Kolkata") -> str:
    """`context/predictions.md`: every prediction with its due date and outcome."""
    zone = ZoneInfo(tz)
    front = yaml.safe_dump({"kind": "predictions", "generated": True}, sort_keys=False)
    lines = [f"---\n{front}---", "", "# Opinions and predictions log", ""]
    for p in predictions:
        status = OUTCOMES.get(p.outcome, "Pending") if p.outcome is not None else "Pending"
        made = p.created_at.astimezone(zone).date().isoformat() if p.created_at else "?"
        lines.append(f"- **{made}** (due {p.due_date.isoformat()} · {status}): {_clean(p.text)}")
        if p.outcome_text:
            lines.append(f"  - What happened: {_clean(p.outcome_text)}")
    return "\n".join(lines) + "\n"


async def sync_predictions_vault(session: AsyncSession, vault_root: Path, tz: str) -> None:
    """Regenerate `context/predictions.md` from the database."""
    rows = (
        (await session.execute(select(Prediction).order_by(Prediction.created_at.desc())))
        .scalars()
        .all()
    )
    write_note(vault_root, CONTEXT_PATH, render_predictions_context(list(rows), tz))
