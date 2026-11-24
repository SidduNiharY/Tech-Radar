from __future__ import annotations

import csv
import io

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from techradar.db.models import Cutoff
from techradar.db.models import TopicWeight as TopicWeightRow
from techradar.exams.weights import (
    MAX_CSV_CHARS,
    MAX_CSV_ROWS,
    CsvRejected,
    CutoffRow,
    ImportReport,
    PyqRow,
    TopicWeight,
    aggregate_weightage,
    gate_weights,
    import_cutoff_text,
    import_cutoffs,
    import_weightage,
    import_weightage_text,
    parse_csv_text,
)

OFFICIAL = frozenset({"ssc.gov.in", "gov.in", "nic.in", "gate2024.iisc.ac.in", "ibps.in"})


def test_cutoff_requires_official_source():
    rows = [
        {
            "exam": "SSC CGL",
            "year": "2025",
            "tier": "1",
            "category": "General",
            "score": "136",
            "source_url": "https://blog.example/x",
        }
    ]
    assert import_cutoffs(rows, OFFICIAL) == []


def test_cutoff_accepts_official_source():
    rows = [
        {
            "exam": "SSC CGL",
            "year": "2025",
            "tier": "1",
            "category": "General",
            "score": "136.5",
            "source_url": "https://ssc.gov.in/notices/cgl_cutoff.pdf",
        }
    ]
    res = import_cutoffs(rows, OFFICIAL)
    assert len(res) == 1
    assert isinstance(res[0], CutoffRow)
    assert res[0].exam == "SSC CGL"
    assert res[0].year == 2025
    assert res[0].tier == "1"
    assert res[0].category == "General"
    assert res[0].score == 136.5
    assert res[0].source_url == "https://ssc.gov.in/notices/cgl_cutoff.pdf"


def test_cutoff_rejects_negative_or_non_numeric_score():
    rows = [
        {
            "exam": "SSC CGL",
            "year": "2025",
            "tier": "1",
            "category": "General",
            "score": "-5",
            "source_url": "https://ssc.gov.in/notices/cgl_cutoff.pdf",
        },
        {
            "exam": "SSC CGL",
            "year": "2025",
            "tier": "1",
            "category": "General",
            "score": "N/A",
            "source_url": "https://ssc.gov.in/notices/cgl_cutoff.pdf",
        },
    ]
    assert import_cutoffs(rows, OFFICIAL) == []


def test_import_weightage():
    rows = [
        {
            "exam": "GATE CS",
            "subject": "Algorithms",
            "topic": "Dynamic Programming",
            "questions": "5",
            "year": "2024",
            "source_url": "https://example.com/analysis",
        }
    ]
    weights = import_weightage(rows)
    assert len(weights) == 1
    w = weights[0]
    assert w.exam == "GATE CS"
    assert w.subject == "Algorithms"
    assert w.topic == "Dynamic Programming"
    assert w.questions == 5
    assert w.year == 2024
    assert w.source == "analysis"


CONFIRMED_ROWS = [
    PyqRow(subject="Algorithms", topic="Dynamic Programming", marks=4.0),
    PyqRow(subject="Algorithms", topic="Graph Algorithms", marks=3.0),
    PyqRow(subject="Operating Systems", topic="Virtual Memory", marks=3.0),
]


def test_gate_weights_sum_to_one():
    weights = gate_weights(CONFIRMED_ROWS)
    assert len(weights) == 3
    assert all(isinstance(w, TopicWeight) for w in weights)
    assert sum(w.share for w in weights) == pytest.approx(1.0)
    dp_weight = next(w for w in weights if w.topic == "Dynamic Programming")
    assert dp_weight.marks_total == 4.0
    assert dp_weight.share == pytest.approx(0.4)


CUTOFF_CSV = (
    "exam,year,tier,category,score,source_url\n"
    "SSC CGL,2025,1,General,136.5,https://ssc.gov.in/notice.pdf\n"
    "SSC CGL,2025,1,OBC,130,https://blog.example/x\n"
)
WEIGHT_CSV = (
    "exam,subject,topic,questions,year,source_url\n"
    "SSC CGL,Quant,Percentages,4,2024,https://blog.example/a\n"
    "SSC CGL,Quant,Percentages,3,2025,https://blog.example/b\n"
    "SSC CGL,English,Idioms,2,2025,\n"
)
OFFICIAL_SSC = frozenset({"ssc.gov.in"})


def test_parse_csv_text_rejects_nul_and_control_characters():
    with pytest.raises(CsvRejected):
        parse_csv_text("exam,year\nSSC\x00,2025\n")
    with pytest.raises(CsvRejected):
        parse_csv_text("exam,year\nSSC\x1b[31m,2025\n")
    assert parse_csv_text("exam,year\nSSC\tCGL,2025\r\n") == [{"exam": "SSC\tCGL", "year": "2025"}]


def test_parse_csv_text_caps_size_and_rows():
    with pytest.raises(CsvRejected):
        parse_csv_text("a\n" + "x" * MAX_CSV_CHARS)
    many = "a\n" + "1\n" * (MAX_CSV_ROWS + 50)
    assert len(parse_csv_text(many)) == MAX_CSV_ROWS


def test_parse_csv_text_rejects_malformed_csv():
    with pytest.raises(CsvRejected):
        parse_csv_text(
            'a,b\n"unterminated,1\n',
        )


def test_out_of_range_year_is_dropped():
    rows = [
        {
            "exam": "SSC",
            "year": y,
            "tier": "1",
            "category": "G",
            "score": "1",
            "source_url": "https://ssc.gov.in/a",
        }
        for y in ("1899", "2101", "-5", "2025")
    ]
    assert [c.year for c in import_cutoffs(rows, OFFICIAL_SSC)] == [2025]
    w = [
        {"exam": "E", "subject": "S", "topic": "T", "questions": "1", "year": y}
        for y in ("1800", "2024")
    ]
    assert [x.year for x in import_weightage(w)] == [2024]


def test_weightage_is_summed_per_topic_and_labelled_unverified_analysis():
    rows = import_weightage(list(csv.DictReader(io.StringIO(WEIGHT_CSV))))
    totals = {(w.subject, w.topic): w.weight for w in aggregate_weightage(rows)}
    assert totals == {("Quant", "Percentages"): 7.0, ("English", "Idioms"): 2.0}
    assert all(w.source == "analysis (unverified)" for w in aggregate_weightage(rows))


class _Nested:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        self.session.savepoints += 1

    async def __aexit__(self, *exc):
        return False


class _FakeSession:
    def __init__(self):
        self.savepoints = 0

    def begin_nested(self):
        return _Nested(self)


async def test_a_poison_file_does_not_stop_the_good_one_next_to_it(monkeypatch):
    stored = []

    async def fake_store(session, cutoffs, weights):
        stored.append((len(cutoffs), len(weights)))

    monkeypatch.setattr("techradar.exams.weights.store_imports", fake_store)
    session, report = _FakeSession(), ImportReport()

    await import_cutoff_text(
        session, "poison.csv", "exam,year\nSSC\x00,2025\n", OFFICIAL_SSC, report
    )
    await import_cutoff_text(session, "good.csv", CUTOFF_CSV, OFFICIAL_SSC, report)
    await import_weightage_text(session, "bad-w.csv", 'a,b\n"x,1\n', report)
    await import_weightage_text(session, "good-w.csv", WEIGHT_CSV, report)

    assert report.rejected == {"poison.csv": "CsvRejected", "bad-w.csv": "CsvRejected"}
    assert (report.cutoffs, report.weights) == (1, 2)
    assert stored == [(1, 0), (0, 2)]
    assert session.savepoints == 2  # each stored file had its own savepoint


async def test_a_failing_store_is_isolated_and_recorded(monkeypatch):
    async def boom(session, cutoffs, weights):
        raise SQLAlchemyError("constraint")

    monkeypatch.setattr("techradar.exams.weights.store_imports", boom)
    report = ImportReport()
    await import_cutoff_text(_FakeSession(), "a.csv", CUTOFF_CSV, OFFICIAL_SSC, report)
    assert report.rejected == {"a.csv": "SQLAlchemyError"} and report.cutoffs == 0


@pytest.mark.db
async def test_store_imports_is_idempotent(session):
    report = ImportReport()
    for _ in range(2):  # the same files again change nothing
        await import_cutoff_text(session, "c.csv", CUTOFF_CSV, OFFICIAL_SSC, report)
        await import_weightage_text(session, "w.csv", WEIGHT_CSV, report)
    assert not report.rejected
    n = (await session.execute(select(func.count()).select_from(Cutoff))).scalar()
    w = (
        await session.execute(
            select(TopicWeightRow.weight).where(TopicWeightRow.topic == "Percentages")
        )
    ).scalar_one()
    assert n >= 1 and w == 7.0


@pytest.mark.db
async def test_a_bad_file_does_not_roll_back_a_good_one(session):
    report = ImportReport()
    await import_weightage_text(session, "good.csv", WEIGHT_CSV, report)
    await import_weightage_text(session, "poison.csv", "a\n\x00\n", report)
    assert list(report.rejected) == ["poison.csv"]
    w = (
        await session.execute(select(TopicWeightRow.weight).where(TopicWeightRow.topic == "Idioms"))
    ).scalar_one()
    assert w == 2.0


def test_gate_weights_empty():
    assert gate_weights([]) == []
