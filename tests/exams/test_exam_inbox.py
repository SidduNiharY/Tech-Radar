"""Cutoffs and weightage CSVs from the library inbox (Phase 8 Task 6 wiring).

Attack tests: a planted symlink, a file swapped between the scan and the open, a folder
swapped for a link, an oversized file, NUL bytes, a hostile file name.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

import techradar.exams.inbox as mod
from techradar.exams.inbox import (
    MAX_CSV_BYTES,
    CsvOutcome,
    csv_handler,
    run_csv_inbox,
)
from techradar.library.inbox import SKIPPED_DIRS, stable_files

NOW = 2_000_000_000.0
OLD = NOW - 3600
CUTOFF_CSV = (
    "exam,year,tier,category,score,source_url\n"
    "SSC CGL,2025,1,General,136.5,https://ssc.gov.in/notices/cgl.pdf\n"
)


def _old(path: Path, data: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    os.utime(path, (OLD, OLD))
    return path


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
        self.handled: list[tuple[str, str, str]] = []

    async def send(self, text: str) -> None:
        self.sent.append(text)

    async def handle(self, kind, shown, text) -> CsvOutcome:  # type: ignore[no-untyped-def]
        self.handled.append((kind, shown, text))
        return CsvOutcome(stored=True, message=f"Imported 1 {kind} from {shown}.")


async def _run(inbox: Path, rec: Rec, session: FakeSession | None = None, **kw) -> int:  # type: ignore[no-untyped-def]
    return await run_csv_inbox(
        session or FakeSession(), inbox, NOW, handle=rec.handle, send=rec.send, **kw
    )


def test_library_intake_skips_the_exam_folders():
    assert {"gate", "cutoffs", "weightage"} <= SKIPPED_DIRS


def test_library_scan_leaves_exam_csvs_alone(tmp_path: Path):
    _old(tmp_path / "cutoffs" / "a.csv", b"x")
    _old(tmp_path / "weightage" / "b.csv", b"x")
    assert stable_files(tmp_path, NOW) == []


async def test_csv_is_stored_then_moved_to_done(tmp_path: Path):
    _old(tmp_path / "cutoffs" / "cgl.csv", CUTOFF_CSV.encode())
    _old(tmp_path / "weightage" / "w.csv", b"exam,subject,topic,questions,year,source_url\n")
    rec, session = Rec(), FakeSession()
    assert await _run(tmp_path, rec, session) == 2
    assert [(k, s) for k, s, _ in rec.handled] == [("cutoffs", "cgl.csv"), ("weightage", "w.csv")]
    assert rec.handled[0][2] == CUTOFF_CSV
    assert (tmp_path / "done" / "cgl.csv").exists() and (tmp_path / "done" / "w.csv").exists()
    assert not (tmp_path / "cutoffs" / "cgl.csv").exists()
    assert session.commits == 2


async def test_unsettled_file_waits(tmp_path: Path):
    f = tmp_path / "cutoffs" / "new.csv"
    f.parent.mkdir()
    f.write_text(CUTOFF_CSV)
    os.utime(f, (NOW - 5, NOW - 5))
    rec = Rec()
    assert await _run(tmp_path, rec) == 0 and f.exists()


async def test_refused_file_goes_to_rejected_with_a_message(tmp_path: Path):
    _old(tmp_path / "cutoffs" / "bad.csv", CUTOFF_CSV.encode())

    async def refuse(kind, shown, text):  # type: ignore[no-untyped-def]
        return CsvOutcome(stored=False, message="no usable rows")

    rec, session = Rec(), FakeSession()
    await run_csv_inbox(session, tmp_path, NOW, handle=refuse, send=rec.send)
    assert (tmp_path / "rejected" / "bad.csv").exists()
    assert rec.sent == ["Couldn't import bad.csv (cutoffs): no usable rows."]
    assert session.rollbacks == 1 and session.commits == 1  # the message only


async def test_oversized_file_is_refused_unread(tmp_path: Path, monkeypatch):
    big = _old(tmp_path / "cutoffs" / "big.csv", b"a" * (MAX_CSV_BYTES + 1))

    def no_open(*a, **k):  # type: ignore[no-untyped-def]
        raise AssertionError("an oversized file must not be opened")

    monkeypatch.setattr(mod, "open_scanned", no_open)
    rec = Rec()
    await _run(tmp_path, rec)
    assert rec.handled == [] and not big.exists()
    assert (tmp_path / "rejected" / "big.csv").exists()
    assert "too large" in rec.sent[0]


async def test_non_utf8_and_wrong_extension_are_refused(tmp_path: Path):
    _old(tmp_path / "cutoffs" / "latin.csv", b"exam\n\xff\xfe\xfa\n")
    _old(tmp_path / "weightage" / "notes.txt", b"hello")
    rec = Rec()
    await _run(tmp_path, rec)
    assert rec.handled == []
    assert sorted(p.name for p in (tmp_path / "rejected").iterdir()) == ["latin.csv", "notes.txt"]
    assert any("not UTF-8" in m for m in rec.sent) and any(".csv files" in m for m in rec.sent)


async def test_planted_symlink_is_never_read(tmp_path: Path):
    inbox = tmp_path / "in"
    secret = tmp_path / "secret.csv"
    secret.write_text("TOKEN")
    (inbox / "cutoffs").mkdir(parents=True)
    (inbox / "cutoffs" / "link.csv").symlink_to(secret)
    rec = Rec()
    assert await _run(inbox, rec) == 0
    assert rec.handled == [] and secret.read_text() == "TOKEN"
    assert (inbox / "cutoffs" / "link.csv").is_symlink()


async def test_cutoffs_folder_that_is_a_link_is_not_scanned(tmp_path: Path):
    inbox = tmp_path / "in"
    inbox.mkdir()
    elsewhere = tmp_path / "elsewhere"
    _old(elsewhere / "x.csv", CUTOFF_CSV.encode())
    (inbox / "cutoffs").symlink_to(elsewhere, target_is_directory=True)
    rec = Rec()
    assert await _run(inbox, rec) == 0
    assert (elsewhere / "x.csv").exists() and rec.handled == []


async def test_file_swapped_for_a_symlink_after_the_scan_is_not_followed(tmp_path, monkeypatch):
    inbox = tmp_path / "in"
    f = _old(inbox / "cutoffs" / "cgl.csv", CUTOFF_CSV.encode())
    secret = tmp_path / "secret.txt"
    secret.write_text("TOKEN")
    real_scan = mod.stable_files

    def scan_then_swap(*a, **k):  # type: ignore[no-untyped-def]
        found = real_scan(*a, **k)
        f.unlink()
        f.symlink_to(secret)
        return found

    monkeypatch.setattr(mod, "stable_files", scan_then_swap)
    rec = Rec()
    await _run(inbox, rec)
    assert rec.handled == [] and rec.sent == []
    assert f.is_symlink() and secret.read_text() == "TOKEN"
    assert not (inbox / "rejected").exists() or not any((inbox / "rejected").iterdir())


async def test_file_replaced_by_another_file_after_the_scan_is_skipped(tmp_path, monkeypatch):
    inbox = tmp_path / "in"
    f = _old(inbox / "cutoffs" / "cgl.csv", CUTOFF_CSV.encode())
    real_scan = mod.stable_files

    def scan_then_replace(*a, **k):  # type: ignore[no-untyped-def]
        found = real_scan(*a, **k)
        f.unlink()
        _old(f, b"exam,year\nother,2020\n")  # a new inode under the same name
        return found

    monkeypatch.setattr(mod, "stable_files", scan_then_replace)
    rec = Rec()
    await _run(inbox, rec)
    assert rec.handled == [] and f.exists()


async def test_folder_swapped_for_a_link_never_moves_outside_files(tmp_path, monkeypatch):
    inbox = tmp_path / "in"
    _old(inbox / "cutoffs" / "sub" / "x.txt", b"not a csv")
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "x.txt").write_bytes(b"precious")
    real_scan = mod.stable_files

    def scan_then_swap(*a, **k):  # type: ignore[no-untyped-def]
        found = real_scan(*a, **k)
        shutil.rmtree(inbox / "cutoffs" / "sub")
        (inbox / "cutoffs" / "sub").symlink_to(vault, target_is_directory=True)
        return found

    monkeypatch.setattr(mod, "stable_files", scan_then_swap)
    await _run(inbox, Rec())
    assert (vault / "x.txt").read_bytes() == b"precious"


async def test_hostile_file_name_is_cleaned_in_messages_and_stays_in_the_inbox(tmp_path: Path):
    name = "x..\\..\\evil‮\n\x1b[31m.txt"  # a leading dot would be skipped as hidden
    _old(tmp_path / "cutoffs" / name, b"x")
    rec = Rec()
    await _run(tmp_path, rec)
    [msg] = rec.sent
    assert "\n" not in msg and "\x1b" not in msg and "‮" not in msg
    [moved] = list((tmp_path / "rejected").iterdir())
    assert moved.parent == tmp_path / "rejected"
    assert not (tmp_path.parent / "evil").exists()


async def test_one_bad_file_never_stops_the_run(tmp_path: Path):
    _old(tmp_path / "cutoffs" / "a.csv", CUTOFF_CSV.encode())
    _old(tmp_path / "cutoffs" / "b.csv", CUTOFF_CSV.encode())
    calls: list[str] = []

    async def flaky(kind, shown, text):  # type: ignore[no-untyped-def]
        calls.append(shown)
        if shown == "a.csv":
            raise RuntimeError("db down")
        return CsvOutcome(stored=True, message="ok")

    session = FakeSession()
    await run_csv_inbox(session, tmp_path, NOW, handle=flaky, send=Rec().send)
    assert calls == ["a.csv", "b.csv"]
    assert (tmp_path / "cutoffs" / "a.csv").exists()  # left for the next run
    assert (tmp_path / "done" / "b.csv").exists() and session.rollbacks == 1


async def test_max_files_per_run(tmp_path: Path):
    for i in range(3):
        _old(tmp_path / "cutoffs" / f"{i}.csv", CUTOFF_CSV.encode())
    rec = Rec()
    assert await _run(tmp_path, rec, max_files=2) == 2
    assert len(rec.handled) == 2


def test_exam_official_domains_cover_exam_bodies_not_blogs():
    from techradar.exams.inbox import exam_official_domains
    from techradar.exams.weights import _is_official_url

    official = exam_official_domains(Path("infra/sources/official_domains.txt"))
    assert _is_official_url("https://ssc.gov.in/x.pdf", official)
    assert _is_official_url("https://gate2025.iitr.ac.in/x.pdf", official)
    assert _is_official_url("https://ibps.in/x.pdf", official)
    assert not _is_official_url("https://gov.in.evil.example/x.pdf", official)
    assert not _is_official_url("https://blog.example/ssc.gov.in", official)


# --- the database handler -------------------------------------------------------------


@pytest.mark.db
async def test_nul_bytes_csv_is_refused_and_nothing_stored(session):
    from sqlalchemy import func, select

    from techradar.db.models import Cutoff

    handle = csv_handler(session, frozenset({"ssc.gov.in"}))
    before = (await session.execute(select(func.count()).select_from(Cutoff))).scalar_one()
    out = await handle("cutoffs", "nul.csv", CUTOFF_CSV.replace("General", "Gen\x00eral"))
    assert not out.stored and "NUL" in out.message
    after = (await session.execute(select(func.count()).select_from(Cutoff))).scalar_one()
    assert after == before


@pytest.mark.db
async def test_official_cutoff_is_stored(session):
    from sqlalchemy import select

    from techradar.db.models import Cutoff

    handle = csv_handler(session, frozenset({"ssc.gov.in"}))
    out = await handle("cutoffs", "cgl.csv", CUTOFF_CSV)
    assert out.stored and out.message == "Imported 1 cutoffs from cgl.csv."
    row = (
        await session.execute(select(Cutoff).where(Cutoff.exam == "SSC CGL", Cutoff.year == 2025))
    ).scalar_one()
    assert row.score == 136.5


@pytest.mark.db
async def test_unofficial_only_file_is_refused(session):
    handle = csv_handler(session, frozenset({"ssc.gov.in"}))
    out = await handle("cutoffs", "blog.csv", CUTOFF_CSV.replace("ssc.gov.in", "blog.example"))
    assert not out.stored and "official source_url" in out.message


@pytest.mark.db
async def test_weightage_is_stored_as_unverified_analysis(session):
    from sqlalchemy import select

    from techradar.db.models import TopicWeight

    handle = csv_handler(session, frozenset())
    text = "exam,subject,topic,questions,year,source_url\nGATE,CS,Paging,3,2024,\n"
    out = await handle("weightage", "w.csv", text)
    assert out.stored
    row = (
        await session.execute(
            select(TopicWeight).where(TopicWeight.exam == "GATE", TopicWeight.topic == "Paging")
        )
    ).scalar_one()
    assert row.source == "analysis (unverified)"
