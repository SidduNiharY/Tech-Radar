from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from techradar.exams.drills.quant import DrillItem
from techradar.exams.final30 import (
    PyqRef,
    capsule_bundle,
    final_30,
    mini_mock,
    write_formula_sheet,
)


def test_final_30_none_without_dates():
    assert final_30({}, date(2026, 11, 8)) is None


def test_final_30_picks_nearest_within_30():
    dates = {"SSC CGL": date(2026, 12, 1), "GATE": date(2027, 2, 1)}
    assert final_30(dates, date(2026, 11, 8)) == "SSC CGL"


def test_final_30_ignores_past_and_distant_exams():
    dates = {
        "Past Exam": date(2026, 11, 1),
        "Distant Exam": date(2027, 1, 1),
    }
    assert final_30(dates, date(2026, 11, 8)) is None


def test_final_30_exam_today():
    today = date(2026, 11, 15)
    dates = {"Today Exam": today}
    assert final_30(dates, today) == "Today Exam"


def test_mini_mock_gate():
    items = mini_mock("GATE CS", date(2026, 11, 15))
    assert len(items) == 20
    assert all(isinstance(item, PyqRef) for item in items)


def test_mini_mock_govt():
    items = mini_mock("SSC CGL", date(2026, 11, 15))
    assert len(items) == 20
    assert all(isinstance(item, DrillItem) for item in items)


def test_mini_mock_deterministic_for_same_day():
    items1 = mini_mock("GATE CS", date(2026, 11, 15))
    items2 = mini_mock("GATE CS", date(2026, 11, 15))
    assert [i.model_dump() for i in items1] == [i.model_dump() for i in items2]


@pytest.mark.asyncio
async def test_write_formula_sheet(tmp_path: Path):
    res = await write_formula_sheet("GATE CS", "Operating Systems", None, tmp_path)
    assert res == "written"

    note_path = tmp_path / "final30" / "GATE CS" / "operating-systems.md"
    assert note_path.exists()
    content = note_path.read_text(encoding="utf-8")
    assert "Operating Systems" in content
    assert "GATE CS" in content


def test_capsule_bundle(tmp_path: Path):
    today = date(2026, 11, 15)
    content = capsule_bundle(tmp_path, today)
    assert isinstance(content, str)

    bundle_path = tmp_path / "final30" / "current-affairs.md"
    assert bundle_path.exists()
    file_content = bundle_path.read_text(encoding="utf-8")
    assert file_content == content
    assert "capsules/2026-10" in content
    assert "capsules/2026-05" in content
