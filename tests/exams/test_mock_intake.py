"""Mock scorecards read by the parser sandbox: stored and answered (Phase 8 Task 5).

A flagged or failed result is never read by a model; invented numbers are refused; a
result file that is a link, too large or of another purpose is left alone.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

import techradar.exams.mock_intake as mod
from techradar.exams.mock_intake import FAILED, collect_mock_results, usable_text
from techradar.exams.mocks import MockScore
from techradar.schemas.pipeline import CleanDoc, IntakeVerdict, ParseResult
from tests.fakes import FakeCompleter

SCORECARD = "Total Score: 123.5 / 200\nQuantitative Aptitude 32.5 / 50\nEnglish 41 / 50"
TODAY = date(2026, 11, 25)


def _result(job_id: str, text: str = SCORECARD, *, verdict="pass", status="ok", purpose="mock"):  # type: ignore[no-untyped-def]
    return ParseResult(
        job_id=job_id,
        kind="image",
        status=status,
        purpose=purpose,
        doc=CleanDoc(url="telegram:mock", title="image", text=text, lang="en")
        if status == "ok"
        else None,
        intake=IntakeVerdict(verdict=verdict, steps=[]),
    )


def _write(clean: Path, r: ParseResult) -> Path:
    clean.mkdir(exist_ok=True)
    p = clean / f"{r.job_id}.result.json"
    p.write_text(r.model_dump_json())
    return p


class FakeSession:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


class Rec:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send(self, text: str) -> None:
        self.sent.append(text)


@pytest.fixture
def stored(monkeypatch) -> list[MockScore]:  # type: ignore[no-untyped-def]
    saved: list[MockScore] = []

    async def fake_store(session, m, *, today, category):  # type: ignore[no-untyped-def]
        saved.append(m)
        return f"saved {m.total}"

    monkeypatch.setattr(mod, "store_mock", fake_store)
    return saved


async def _collect(clean: Path, completer=None, session=None) -> tuple[int, Rec]:  # type: ignore[no-untyped-def]
    rec = Rec()
    n = await collect_mock_results(
        session or FakeSession(),
        clean,
        completer or FakeCompleter([]),
        today=TODAY,
        category="General",
        send=rec.send,
    )
    return n, rec


def test_only_unflagged_ok_results_are_usable():
    assert usable_text(_result("a" * 32)) == SCORECARD
    assert usable_text(_result("a" * 32, verdict="flag")) is None
    assert usable_text(_result("a" * 32, status="rejected")) is None
    assert usable_text(_result("a" * 32, status="empty")) is None


async def test_regex_scorecard_is_stored_and_answered(tmp_path: Path, stored):  # type: ignore[no-untyped-def]
    p = _write(tmp_path / "clean", _result("a" * 32))
    session = FakeSession()
    n, rec = await _collect(tmp_path / "clean", session=session)
    assert n == 1 and rec.sent == ["saved 123.5"] and stored[0].total == 123.5
    assert not p.exists() and session.commits == 1


async def test_flagged_scorecard_never_reaches_the_model(tmp_path: Path, stored):  # type: ignore[no-untyped-def]
    _write(tmp_path / "clean", _result("a" * 32, "garbled", verdict="flag"))
    completer = FakeCompleter(['{"exam":"SSC","total":150,"max_total":200,"sections":[]}'])
    n, rec = await _collect(tmp_path / "clean", completer)
    assert rec.sent == [FAILED] and stored == [] and completer.calls == []


async def test_invented_numbers_from_the_model_are_refused(tmp_path: Path, stored):  # type: ignore[no-untyped-def]
    _write(tmp_path / "clean", _result("a" * 32, "garbled 123.5 / 200"))
    completer = FakeCompleter(['{"exam":"SSC","total":150,"max_total":200,"sections":[]}'])
    _, rec = await _collect(tmp_path / "clean", completer)
    assert rec.sent == [FAILED] and stored == []


async def test_other_purposes_links_and_forged_names_are_left_alone(tmp_path: Path, stored):  # type: ignore[no-untyped-def]
    clean = tmp_path / "clean"
    news = _write(clean, _result("b" * 32, purpose="news"))
    target = tmp_path / "elsewhere.json"
    target.write_text(_result("c" * 32).model_dump_json())
    link = clean / f"{'c' * 32}.result.json"
    link.symlink_to(target)
    forged = clean / f"{'d' * 32}.result.json"  # claims another job id
    forged.write_text(_result("e" * 32).model_dump_json())
    big = clean / f"{'f' * 32}.result.json"
    big.write_bytes(b" " * (mod.MAX_RESULT_BYTES + 1))
    n, rec = await _collect(clean)
    assert n == 0 and rec.sent == [] and stored == []
    assert news.exists() and link.is_symlink() and forged.exists() and big.exists()


async def test_a_failing_result_is_rolled_back_and_kept(tmp_path: Path, monkeypatch):  # type: ignore[no-untyped-def]
    p = _write(tmp_path / "clean", _result("a" * 32))

    async def boom(session, m, *, today, category):  # type: ignore[no-untyped-def]
        raise RuntimeError("db down")

    monkeypatch.setattr(mod, "store_mock", boom)
    session = FakeSession()
    n, _ = await _collect(tmp_path / "clean", session=session)
    assert n == 0 and p.exists() and session.rollbacks == 1


@pytest.mark.db
async def test_mock_is_stored_and_compared_with_the_latest_cutoff(session):
    from sqlalchemy import select

    from techradar.db.models import Cutoff, MockResult

    session.add_all(
        [
            Cutoff(
                exam="Mock",
                year=2023,
                tier="1",
                category="General",
                score=120.0,
                source_url="https://ssc.gov.in/a",
            ),
            Cutoff(
                exam="Mock",
                year=2024,
                tier="1",
                category="General",
                score=136.0,
                source_url="https://ssc.gov.in/b",
            ),
        ]
    )
    await session.flush()
    from techradar.exams.mocks import extract_mock_regex

    m = extract_mock_regex(SCORECARD)
    assert m is not None
    reply = await mod.store_mock(session, m, today=TODAY, category="General")
    assert reply.splitlines()[1] == "You're 12.5 marks below last year's cutoff (136.0, General)."
    row = (
        (await session.execute(select(MockResult).where(MockResult.taken_on == TODAY)))
        .scalars()
        .first()
    )
    assert row is not None and row.total == 123.5 and row.source == "screenshot"
