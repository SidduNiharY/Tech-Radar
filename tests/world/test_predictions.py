from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import Outbox
from techradar.world.predictions import (
    get_due_predictions,
    parse_predict,
    record_outcome,
    record_prediction,
    reminder_buttons,
    render_reminder,
    run_prediction_reminder,
    set_outcome_text,
    sync_predictions_vault,
)

TODAY = date(2026, 11, 8)


def test_parse_predict() -> None:
    assert parse_predict("Rates fall by 2027-03-31", TODAY) == ("Rates fall", date(2027, 3, 31))
    assert parse_predict("Rates fall by 2025-01-01", TODAY) == "Pick a future date."
    assert parse_predict("Rates fall", TODAY).startswith("Use: /predict")
    assert parse_predict("x" * 281, TODAY) == "Keep it under 280 characters."


def test_parse_predict_edge_cases() -> None:
    # "by" inside the text is fine: only the last " by <date>" counts
    assert parse_predict("Led by Rao, GDP up by 2027-03-31", TODAY) == (
        "Led by Rao, GDP up",
        date(2027, 3, 31),
    )
    assert parse_predict(f"{'x' * 281} by 2027-03-31", TODAY) == "Keep it under 280 characters."
    assert parse_predict("x" * 280 + " by 2027-03-31", TODAY) == ("x" * 280, date(2027, 3, 31))
    assert parse_predict("by 2027-03-31", TODAY).startswith("Use:")
    assert parse_predict("Rates fall by 2027-13-45", TODAY).startswith("Use:")
    assert parse_predict("Rates fall by 20270331", TODAY).startswith("Use:")
    assert parse_predict("Rates fall by 2026-11-08", TODAY) == "Pick a future date."
    assert parse_predict("", TODAY).startswith("Use:")
    assert parse_predict("रेपो दर घटेगी by 2027-03-31", TODAY) == (
        "रेपो दर घटेगी",
        date(2027, 3, 31),
    )


def test_reminder_text_and_buttons_match_the_plan() -> None:
    assert render_reminder("Rates fall", date(2026, 11, 8)) == (
        "🔮 Your prediction from 8 Nov: Rates fall. What happened? Reply to this message."
    )
    row = reminder_buttons(7)[0]
    assert [(b.text, b.data) for b in row] == [
        ("Right", "pred:7:1"),
        ("Wrong", "pred:7:2"),
        ("Partly", "pred:7:3"),
    ]


pytestmark_db = pytest.mark.db


@pytest.mark.db
async def test_due_predictions_selected_once(session: AsyncSession) -> None:
    pid = await record_prediction(session, "Inflation falls", date(2026, 11, 10))
    assert [p.id for p in await get_due_predictions(session, date(2026, 11, 15))] == [pid]
    assert await get_due_predictions(session, date(2026, 11, 9)) == []

    now = datetime(2026, 11, 15, 2, 30, tzinfo=UTC)
    assert (
        await run_prediction_reminder(session, now=now, owner_chat_id=4242, tz="Asia/Kolkata") == 1
    )
    assert (
        await run_prediction_reminder(session, now=now, owner_chat_id=4242, tz="Asia/Kolkata") == 0
    )
    msgs = (
        (await session.execute(select(Outbox).where(Outbox.purpose == "prediction")))
        .scalars()
        .all()
    )
    assert [(m.chat_id, m.ref_id) for m in msgs if m.ref_id == pid] == [(4242, pid)]
    assert msgs[-1].buttons[0][0]["data"] == f"pred:{pid}:1"


@pytest.mark.db
async def test_an_answered_prediction_is_not_reminded(session: AsyncSession) -> None:
    pid = await record_prediction(session, "Inflation falls", date(2026, 11, 10))
    assert await record_outcome(session, pid, 1, "CPI fell to 4.5%")
    assert await get_due_predictions(session, date(2026, 11, 15)) == []


@pytest.mark.db
async def test_outcome_rules(session: AsyncSession) -> None:
    pid = await record_prediction(session, "Gold up", date(2026, 12, 1))
    assert not await record_outcome(session, pid, 9)  # not 1 to 3
    assert not await record_outcome(session, -1, 1)  # unknown
    assert await record_outcome(session, pid, 3)
    assert not await record_outcome(session, pid, 2)  # already answered, no overwrite
    assert await set_outcome_text(session, pid, "  half\nright ")
    assert not await set_outcome_text(session, pid, "   ")


@pytest.mark.db
async def test_context_page_lists_every_prediction(session: AsyncSession, tmp_path: Path) -> None:
    pid = await record_prediction(session, "Rates fall", date(2027, 3, 31))
    await record_prediction(session, "रेपो दर घटेगी", date(2027, 4, 1))
    await record_outcome(session, pid, 1, "They did")
    await sync_predictions_vault(session, tmp_path, "Asia/Kolkata")
    text = (tmp_path / "context" / "predictions.md").read_text(encoding="utf-8")
    assert "generated: true" in text and "Rates fall" in text and "Right" in text
    assert "What happened: They did" in text and "रेपो दर घटेगी" in text and "Pending" in text
