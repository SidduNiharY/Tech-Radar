"""GATE past papers from library-inbox/gate/<year>/ (Phase 8 Task 2 wiring).

Attack tests: a planted symlink, a file swapped after the scan, an oversized file, a ZIP
renamed .pdf, a year out of range, path tricks in names and folders, a flagged result,
a forged or linked result file. One test runs a pair through the real Intake Gateway and
parser sandbox (no network, 120 s per job).
"""

from __future__ import annotations

import io
import json
import os
import zipfile
from datetime import date
from pathlib import Path

import pytest
import yaml

import techradar.exams.inbox as inbox_mod
from techradar.exams.pyq_intake import (
    MAX_GATE_PDF_BYTES,
    PyqPair,
    _apply_pair,
    build_pyq_rows,
    collect_pyq_results,
    normalise_key,
    parse_gate_name,
    queue_gate_papers,
    read_result,
)
from techradar.intake.av import AvResult
from techradar.parser.main import build_gate, serve_once
from techradar.schemas.pipeline import CleanDoc, IntakeVerdict, ParseJob, ParseResult

NOW = 1_795_000_000.0  # 2026-11-17
OLD = NOW - 3600
LIMITS = yaml.safe_load(Path("infra/intake/limits.yaml").read_text())

PAPER_TEXT = """GATE 2024 Computer Science and Information Technology (CS1)
General instructions: answer every question. This paper has three questions.
Q. 1 Which of the following is a power of 2?
(A) 3
(B) 4
(C) 6
(D) 10
Q. 2 Which of these are sorting algorithms?
(A) Merge sort
(B) Dijkstra
(C) Heap sort
(D) Prim
Q. 3 Compute 1.5 + 0.05 rounded to two decimals.
"""
KEY_TEXT = """GATE 2024 CS1 official answer key, released by the organising institute.
Candidates may compare their responses with these keys; marks are as printed.
Q.No Type Section Key Marks (rows below, one per question of the paper)
1 MCQ GA B 1
2 MSQ CS C;A 2
3 NAT CS 1.5 to 1.6 2
"""


def _text_pdf(text: str) -> bytes:
    """A small, clean one-page PDF with a text layer (Helvetica), built by hand."""
    lines = []
    for line in text.splitlines():
        esc = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        lines.append(f"({esc}) Tj 0 -14 Td")
    stream = ("BT /F1 10 Tf 40 800 Td " + " ".join(lines) + " ET").encode("latin-1")
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs, 1):
        offsets.append(out.tell())
        out.write(b"%d 0 obj\n" % i + body + b"\nendobj\n")
    xref = out.tell()
    out.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1))
    for off in offsets:
        out.write(b"%010d 00000 n \n" % off)
    out.write(
        b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    )
    return out.getvalue()


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

    async def send(self, text: str) -> None:
        self.sent.append(text)


class Dirs:
    def __init__(self, root: Path) -> None:
        self.inbox = root / "library-inbox"
        self.inbox.mkdir()
        self.raw = root / "raw"
        self.jobs = root / "parse-jobs"
        self.clean = root / "clean"
        self.records = root / "library" / "exam-jobs"
        self.quarantine = root / "quarantine"


async def _queue(d: Dirs, rec: Rec, session: FakeSession | None = None) -> int:
    return await queue_gate_papers(
        session or FakeSession(), d.inbox, d.raw, d.jobs, d.records, NOW, send=rec.send
    )


def _jobs(d: Dirs) -> list[ParseJob]:
    if not d.jobs.exists():
        return []
    return [ParseJob.model_validate_json(p.read_text()) for p in sorted(d.jobs.glob("*.job.json"))]


# --- names, years, keys ---------------------------------------------------------------


def test_gate_name_rules():
    ok = parse_gate_name(("2024", "cs1-2024.pdf"), NOW)
    assert not isinstance(ok, str) and (ok.year, ok.paper, ok.role) == (2024, "CS1", "paper")
    key = parse_gate_name(("2024", "CS1-2024-KEY.PDF"), NOW)
    assert not isinstance(key, str) and key.role == "key" and key.paper == "CS1"
    for parts in [
        ("1850", "cs-1850.pdf"),  # too old
        ("2999", "cs-2999.pdf"),  # in the future
        ("20x4", "cs-2024.pdf"),
        ("2024", "cs-2023.pdf"),  # name and folder years differ
        ("2024", "cs-2024.pdf.exe"),
        ("2024", "..-2024.pdf"),
        ("2024", "cs-2024.pdf\n"),
        ("2024", "c/s-2024.pdf"),
        ("cs-2024.pdf",),  # not in a year folder
        ("2024", "sub", "cs-2024.pdf"),
    ]:
        assert isinstance(parse_gate_name(parts, NOW), str), parts


def test_normalise_key():
    assert normalise_key("MCQ", " b ") == "B"
    assert normalise_key("MCQ", "E") is None
    assert normalise_key("MSQ", "C;A") == "A;C"
    assert normalise_key("MSQ", "A;Z") is None
    assert normalise_key("NAT", "1.5 to 1.6") == "1.5 to 1.6"
    assert normalise_key("NAT", "1.6 to 1.5") is None
    assert normalise_key("NAT", "-3") == "-3"
    assert normalise_key("NAT", "drop table") is None


def test_build_rows_keeps_only_questions_with_a_valid_key():
    rows, left_out = build_pyq_rows(PAPER_TEXT, KEY_TEXT.replace("1 MCQ GA B 1", "1 MCQ GA Q 1"))
    assert [r.number for r in rows] == [2, 3] and left_out == 1
    assert rows[0].answer_key == "A;C" and rows[1].qtype == "NAT"


# --- taking pairs ----------------------------------------------------------------------


async def test_pair_is_copied_recorded_and_queued(tmp_path: Path):
    d = Dirs(tmp_path)
    paper = _text_pdf(PAPER_TEXT)
    _old(d.inbox / "gate" / "2024" / "cs1-2024.pdf", paper)
    _old(d.inbox / "gate" / "2024" / "cs1-2024-key.pdf", _text_pdf(KEY_TEXT))
    rec, session = Rec(), FakeSession()
    assert await _queue(d, rec, session) == 1
    jobs = _jobs(d)
    assert {j.url for j in jobs} == {"library:gate/2024/CS1", "library:gate/2024/CS1-key"}
    assert all(j.purpose == "pyq" and j.kind == "pdf" and j.origin == "library" for j in jobs)
    assert all(j.raw_name.endswith(".pdf") and "cs1" not in j.raw_name for j in jobs)
    import hashlib

    paper_job = next(j for j in jobs if not j.url.endswith("-key"))
    assert paper_job.raw_name == hashlib.sha256(paper).hexdigest() + ".pdf"
    assert (d.raw / paper_job.raw_name).read_bytes() == paper
    [record] = list(d.records.iterdir())
    pair = PyqPair.model_validate_json(record.read_text())
    assert (pair.year, pair.paper) == (2024, "CS1")
    assert {pair.paper_job, pair.key_job} == {j.job_id for j in jobs}
    assert sorted(p.name for p in (d.inbox / "done").iterdir()) == [
        "cs1-2024-key.pdf",
        "cs1-2024.pdf",
    ]
    assert rec.sent == ["Reading GATE CS1 2024 (paper and answer key) for the bank."]
    assert session.commits == 1


async def test_half_a_pair_waits(tmp_path: Path):
    d = Dirs(tmp_path)
    f = _old(d.inbox / "gate" / "2024" / "cs-2024.pdf", _text_pdf(PAPER_TEXT))
    rec = Rec()
    assert await _queue(d, rec) == 0
    assert f.exists() and _jobs(d) == [] and rec.sent == []


async def test_bad_year_and_names_are_rejected(tmp_path: Path):
    d = Dirs(tmp_path)
    pdf = _text_pdf(PAPER_TEXT)
    _old(d.inbox / "gate" / "1850" / "cs-1850.pdf", pdf)
    _old(d.inbox / "gate" / "2024" / "notes.pdf", pdf)
    _old(d.inbox / "gate" / "2024" / "deep" / "cs-2024.pdf", pdf)
    _old(d.inbox / "gate" / "x..\\..\\cs-2024.pdf", pdf)
    rec = Rec()
    assert await _queue(d, rec) == 0
    assert len(list((d.inbox / "rejected").iterdir())) == 4 and _jobs(d) == []
    assert any("year must be between 1991" in m for m in rec.sent)
    assert all("\\" not in m.split(":")[1] for m in rec.sent)


async def test_zip_renamed_pdf_is_rejected(tmp_path: Path):
    d = Dirs(tmp_path)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("a.txt", "%PDF-1.4 inside a zip")
    _old(d.inbox / "gate" / "2024" / "cs-2024.pdf", buf.getvalue())
    _old(d.inbox / "gate" / "2024" / "cs-2024-key.pdf", _text_pdf(KEY_TEXT))
    rec = Rec()
    assert await _queue(d, rec) == 0
    assert (d.inbox / "rejected" / "cs-2024.pdf").exists() and _jobs(d) == []
    assert rec.sent == ["Couldn't add cs-2024.pdf to the GATE bank: it is not a PDF."]
    assert (d.inbox / "gate" / "2024" / "cs-2024-key.pdf").exists()  # waits for a new paper


async def test_oversized_pdf_is_refused_unread(tmp_path: Path, monkeypatch):
    d = Dirs(tmp_path)
    big = _old(d.inbox / "gate" / "2024" / "cs-2024.pdf", b"%PDF-1.4\n")
    os.truncate(big, MAX_GATE_PDF_BYTES + 1)
    os.utime(big, (OLD, OLD))
    _old(d.inbox / "gate" / "2024" / "cs-2024-key.pdf", _text_pdf(KEY_TEXT))
    import techradar.exams.pyq_intake as mod

    real_open = mod.open_scanned
    opened: list[str] = []

    def spy(inbox, f):  # type: ignore[no-untyped-def]
        opened.append(f.path.name)
        return real_open(inbox, f)

    monkeypatch.setattr(mod, "open_scanned", spy)
    rec = Rec()
    await _queue(d, rec)
    assert "cs-2024.pdf" not in opened
    assert (d.inbox / "rejected" / "cs-2024.pdf").exists() and "too large" in rec.sent[0]


async def test_planted_symlink_is_never_read(tmp_path: Path):
    d = Dirs(tmp_path)
    secret = tmp_path / "secret.pdf"
    secret.write_bytes(_text_pdf("TOKEN " * 50))
    (d.inbox / "gate" / "2024").mkdir(parents=True)
    (d.inbox / "gate" / "2024" / "cs-2024.pdf").symlink_to(secret)
    _old(d.inbox / "gate" / "2024" / "cs-2024-key.pdf", _text_pdf(KEY_TEXT))
    assert await _queue(d, Rec()) == 0
    assert _jobs(d) == [] and not d.raw.exists()


async def test_gate_folder_that_is_a_link_is_not_scanned(tmp_path: Path):
    d = Dirs(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    _old(elsewhere / "2024" / "cs-2024.pdf", _text_pdf(PAPER_TEXT))
    _old(elsewhere / "2024" / "cs-2024-key.pdf", _text_pdf(KEY_TEXT))
    (d.inbox / "gate").symlink_to(elsewhere, target_is_directory=True)
    assert await _queue(d, Rec()) == 0
    assert (elsewhere / "2024" / "cs-2024.pdf").exists() and _jobs(d) == []


async def test_file_swapped_after_the_scan_is_not_copied(tmp_path: Path, monkeypatch):
    d = Dirs(tmp_path)
    paper = _old(d.inbox / "gate" / "2024" / "cs-2024.pdf", _text_pdf(PAPER_TEXT))
    _old(d.inbox / "gate" / "2024" / "cs-2024-key.pdf", _text_pdf(KEY_TEXT))
    secret = tmp_path / "secret.pdf"
    secret.write_bytes(_text_pdf("TOKEN " * 50))
    import techradar.exams.pyq_intake as mod

    real_scan = mod.stable_files

    def scan_then_swap(*a, **k):  # type: ignore[no-untyped-def]
        found = real_scan(*a, **k)
        paper.unlink()
        paper.symlink_to(secret)
        return found

    monkeypatch.setattr(mod, "stable_files", scan_then_swap)
    rec, session = Rec(), FakeSession()
    assert await _queue(d, rec, session) == 0
    assert _jobs(d) == [] and paper.is_symlink() and session.rollbacks == 1
    assert not d.raw.exists() or not any(d.raw.iterdir())


def test_exams_inbox_helpers_are_shared():
    assert inbox_mod.open_scanned is not None  # pyq intake reads through the same door


# --- collecting results ----------------------------------------------------------------


def _pair(created: float = NOW) -> PyqPair:
    return PyqPair(year=2024, paper="CS1", paper_job="a" * 32, key_job="b" * 32, created=created)


def _result(job_id: str, text: str, verdict: str = "pass", status: str = "ok") -> ParseResult:
    return ParseResult(
        job_id=job_id,
        kind="pdf",
        status=status,  # type: ignore[arg-type]
        purpose="pyq",
        doc=CleanDoc(url="library:gate/2024/CS1", title="t", text=text, lang="en")
        if status == "ok"
        else None,
        intake=IntakeVerdict(verdict=verdict, steps=[]),  # type: ignore[arg-type]
    )


def _write_pair(d: Dirs, pair: PyqPair) -> None:
    d.records.mkdir(parents=True, exist_ok=True)
    (d.records / f"{pair.paper_job}.json").write_text(pair.model_dump_json())


def _write_result(d: Dirs, r: ParseResult) -> None:
    d.clean.mkdir(parents=True, exist_ok=True)
    (d.clean / f"{r.job_id}.result.json").write_text(r.model_dump_json())


async def test_flagged_paper_is_never_used_for_questions():
    rec = Rec()
    pair = _pair()
    await _apply_pair(
        None,  # type: ignore[arg-type]  # refused before any database access
        pair,
        _result(pair.paper_job, PAPER_TEXT, verdict="flag"),
        _result(pair.key_job, KEY_TEXT),
        rec.send,
    )
    assert rec.sent == [
        "Couldn't add GATE CS1 2024 to the bank: the intake checks marked the paper 'flag', "
        "so it is not used for questions."
    ]


async def test_rejected_key_is_reported():
    rec = Rec()
    pair = _pair()
    await _apply_pair(
        None,  # type: ignore[arg-type]
        pair,
        _result(pair.paper_job, PAPER_TEXT),
        _result(pair.key_job, KEY_TEXT, status="rejected"),
        rec.send,
    )
    assert "the key could not be read (rejected)" in rec.sent[0]


def test_result_that_is_a_link_or_foreign_counts_as_an_error(tmp_path: Path):
    d = Dirs(tmp_path)
    d.clean.mkdir()
    elsewhere = tmp_path / "x.json"
    elsewhere.write_text(_result("a" * 32, PAPER_TEXT).model_dump_json())
    (d.clean / f"{'a' * 32}.result.json").symlink_to(elsewhere)
    assert read_result(d.clean, "a" * 32).status == "error"  # type: ignore[union-attr]
    # a result that claims another job or purpose
    other = _result("c" * 32, PAPER_TEXT).model_dump_json()
    (d.clean / f"{'b' * 32}.result.json").write_text(other)
    assert read_result(d.clean, "b" * 32).status == "error"  # type: ignore[union-attr]
    news = _result("e" * 32, PAPER_TEXT).model_copy(update={"purpose": "news"})
    _write_result(d, news)
    assert read_result(d.clean, "e" * 32).status == "error"  # type: ignore[union-attr]
    assert read_result(d.clean, "f" * 32) is None


async def test_collect_waits_for_both_results_then_applies(tmp_path: Path, monkeypatch):
    d = Dirs(tmp_path)
    pair = _pair()
    _write_pair(d, pair)
    _write_result(d, _result(pair.paper_job, PAPER_TEXT))
    applied: list[tuple[str, str]] = []

    async def fake_apply(session, p, paper, key, send):  # type: ignore[no-untyped-def]
        applied.append((paper.doc.text, key.doc.text))

    import techradar.exams.pyq_intake as mod

    monkeypatch.setattr(mod, "_apply_pair", fake_apply)
    session = FakeSession()
    assert await collect_pyq_results(session, d.records, d.clean, NOW, send=Rec().send) == 0
    _write_result(d, _result(pair.key_job, KEY_TEXT))
    assert await collect_pyq_results(session, d.records, d.clean, NOW, send=Rec().send) == 1
    assert applied == [(PAPER_TEXT, KEY_TEXT)] and session.commits == 1
    assert not any(d.clean.iterdir()) and not any(d.records.iterdir())


async def test_pair_missing_a_result_is_given_up_after_a_day(tmp_path: Path):
    d = Dirs(tmp_path)
    pair = _pair(created=NOW - 2 * 86400)
    _write_pair(d, pair)
    rec = Rec()
    assert await collect_pyq_results(FakeSession(), d.records, d.clean, NOW, send=rec.send) == 1  # type: ignore[arg-type]
    assert "did not finish" in rec.sent[0] and not any(d.records.iterdir())


async def test_bad_record_is_removed(tmp_path: Path):
    d = Dirs(tmp_path)
    d.records.mkdir(parents=True)
    (d.records / f"{'a' * 32}.json").write_text(json.dumps({"year": 1850}))
    assert await collect_pyq_results(FakeSession(), d.records, d.clean, NOW, send=Rec().send) == 0  # type: ignore[arg-type]
    assert not any(d.records.iterdir())


# --- end to end through the Intake Gateway and the parser sandbox ---------------------


class FakeAv:
    def scan(self, path: Path) -> AvResult:
        return AvResult(status="clean", db_date=date.today())


async def test_pair_through_the_gateway_and_sandbox_gives_questions(tmp_path: Path):
    d = Dirs(tmp_path)
    _old(d.inbox / "gate" / "2024" / "cs1-2024.pdf", _text_pdf(PAPER_TEXT))
    _old(d.inbox / "gate" / "2024" / "cs1-2024-key.pdf", _text_pdf(KEY_TEXT))
    assert await _queue(d, Rec()) == 1
    gate = build_gate(
        d.raw,
        d.quarantine,
        av=FakeAv(),
        allowed_hosts=frozenset(),
        limits=LIMITS,
        library_dir=tmp_path / "library",
    )
    assert serve_once(d.jobs, d.raw, d.clean, gate=gate) == 2
    [record] = list(d.records.iterdir())
    pair = PyqPair.model_validate_json(record.read_text())
    paper, key = read_result(d.clean, pair.paper_job), read_result(d.clean, pair.key_job)
    assert paper is not None and key is not None
    assert paper.status == "ok" and paper.intake and paper.intake.verdict == "pass"
    assert paper.doc and key.doc
    rows, left_out = build_pyq_rows(paper.doc.text, key.doc.text)
    assert [(r.number, r.qtype, r.answer_key) for r in rows] == [
        (1, "MCQ", "B"),
        (2, "MSQ", "A;C"),
        (3, "NAT", "1.5 to 1.6"),
    ]
    assert left_out == 0


# --- the database ------------------------------------------------------------------------


@pytest.mark.db
async def test_pair_is_stored_once(session):
    from sqlalchemy import select

    from techradar.db.models import PyqQuestion

    pair = PyqPair(year=2003, paper="CS", paper_job="a" * 32, key_job="b" * 32, created=NOW)
    rec = Rec()
    paper, key = _result(pair.paper_job, PAPER_TEXT), _result(pair.key_job, KEY_TEXT)
    await _apply_pair(session, pair, paper, key, rec.send)
    rows = (
        (
            await session.execute(
                select(PyqQuestion)
                .where(PyqQuestion.exam == "GATE", PyqQuestion.year == 2003)
                .order_by(PyqQuestion.number)
            )
        )
        .scalars()
        .all()
    )
    assert [(r.number, r.answer_key, r.tag_status) for r in rows] == [
        (1, "B", "none"),
        (2, "A;C", "none"),
        (3, "1.5 to 1.6", "none"),
    ]
    assert rec.sent[-1] == "GATE CS 2003: 3 questions saved to the past-paper bank."
    await _apply_pair(session, pair, paper, key, rec.send)
    assert rec.sent[-1] == "GATE CS 2003 is already in the bank (3 questions)."
