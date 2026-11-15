from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pytest

from techradar.world.predictions import (
    get_due_predictions,
    parse_predict,
    record_outcome,
    record_prediction,
)


def test_parse_predict() -> None:
    assert parse_predict("Rates fall by 2027-03-31", date(2026, 11, 8)) == (
        "Rates fall",
        date(2027, 3, 31),
    )
    assert parse_predict("Rates fall by 2025-01-01", date(2026, 11, 8)) == "Pick a future date."
    assert parse_predict("Rates fall", date(2026, 11, 8)).startswith("Use: /predict")
    assert parse_predict("x" * 281, date(2026, 11, 8)) == "Keep it under 280 characters."


@pytest.mark.db
async def test_due_predictions_selected_once(session: Any, tmp_path: Path) -> None:
    pid = await record_prediction(
        session, "Inflation falls", date(2026, 11, 10), vault_root=tmp_path
    )
    due = await get_due_predictions(session, date(2026, 11, 15))
    assert len(due) == 1
    assert due[0].id == pid

    await record_outcome(
        session, pid, outcome=1, outcome_text="CPI fell to 4.5%", vault_root=tmp_path
    )
    due_after = await get_due_predictions(session, date(2026, 11, 15))
    assert len(due_after) == 0
