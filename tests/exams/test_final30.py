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
from techradar.rag.answer import Answer, Citation


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


def _bank(n: int) -> list[PyqRef]:
    return [PyqRef(exam="GATE CS", year=2023, paper="CS", number=i) for i in range(1, n + 1)]


def test_mini_mock_gate_picks_from_the_bank_only():
    bank = _bank(60)
    items = mini_mock("GATE CS", date(2026, 11, 15), bank)
    assert len(items) == 20
    assert all(isinstance(item, PyqRef) for item in items)
    assert all(item in bank for item in items)
    assert len({i.number for i in items}) == 20  # no question twice


def test_mini_mock_gate_with_a_thin_bank_is_shorter_not_invented():
    assert mini_mock("GATE CS", date(2026, 11, 15)) == []
    assert len(mini_mock("GATE CS", date(2026, 11, 15), _bank(5))) == 5


def test_mini_mock_govt():
    items = mini_mock("SSC CGL", date(2026, 11, 15))
    assert len(items) == 20
    assert all(isinstance(item, DrillItem) for item in items)


def test_mini_mock_deterministic_for_same_day():
    bank = _bank(60)
    items1 = mini_mock("GATE CS", date(2026, 11, 15), bank)
    items2 = mini_mock("GATE CS", date(2026, 11, 15), bank)
    assert [i.model_dump() for i in items1] == [i.model_dump() for i in items2]
    other = mini_mock("GATE CS", date(2026, 11, 16), bank)
    assert [i.number for i in other] != [i.number for i in items1]


def _answer(status: str, text: str = "x") -> Answer:
    cites = [
        Citation(n=1, doc_path="library/os.md", title="Galvin ch 8", heading="", verified=None)
    ]
    return Answer(
        text=text,
        citations=cites if status == "answered" else [],
        status=status,  # type: ignore[arg-type]
        used_unverified=False,
        flags=[],
    )


def _fake_answer(monkeypatch: pytest.MonkeyPatch, answer: Answer) -> list[str]:
    asked: list[str] = []

    async def fake(question: str, deps: object, *a: object, **k: object) -> Answer:
        asked.append(question)
        return answer

    monkeypatch.setattr("techradar.exams.final30.answer_question", fake)
    return asked


@pytest.mark.asyncio
async def test_write_formula_sheet_is_grounded_and_cited(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    asked = _fake_answer(monkeypatch, _answer("answered", "Banker's safety check [C1]"))
    res = await write_formula_sheet("GATE CS", "Operating Systems", object(), tmp_path)  # type: ignore[arg-type]
    assert res == "written"
    assert "Operating Systems" in asked[0]

    note = tmp_path / "final30" / "gate-cs" / "operating-systems.md"
    text = note.read_text(encoding="utf-8")
    assert "Banker's safety check [C1]" in text
    assert "library/os.md" in text and "Galvin ch 8" in text
    assert "generated: true" in text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "expected"),
    [("not_found", "not_enough_sources"), ("needs_review", "needs_review")],
)
async def test_write_formula_sheet_writes_nothing_without_a_checked_answer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, status: str, expected: str
):
    _fake_answer(monkeypatch, _answer(status))
    res = await write_formula_sheet("GATE CS", "Operating Systems", object(), tmp_path)  # type: ignore[arg-type]
    assert res == expected
    assert not (tmp_path / "final30").exists()


@pytest.mark.asyncio
async def test_write_formula_sheet_cannot_escape_the_vault(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _fake_answer(monkeypatch, _answer("answered", "ok [C1]"))
    vault = tmp_path / "vault"
    vault.mkdir()
    await write_formula_sheet("../../evil", "../x", object(), vault)  # type: ignore[arg-type]
    assert not (tmp_path / "evil").exists()
    assert list(vault.rglob("*.md")) and all(
        p.resolve().is_relative_to(vault.resolve()) for p in vault.rglob("*.md")
    )


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
