from __future__ import annotations

import csv
import io

import pytest
from sqlalchemy import func, select

from techradar.db.models import Cutoff
from techradar.db.models import TopicWeight as TopicWeightRow
from techradar.exams.weights import (
    MAX_CSV_BYTES,
    CutoffRow,
    PyqRow,
    TopicWeight,
    aggregate_weightage,
    gate_weights,
    import_cutoffs,
    import_inbox_files,
    import_weightage,
    read_csv_rows,
    store_imports,
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


def test_read_csv_rows_reads_only_regular_csv_files_and_caps_size(tmp_path):
    folder = tmp_path / "cutoffs"
    folder.mkdir()
    (folder / "a.csv").write_text(CUTOFF_CSV, encoding="utf-8")
    (folder / "notes.txt").write_text("ignore", encoding="utf-8")
    (folder / "big.csv").write_bytes(b"x" * (MAX_CSV_BYTES + 1))
    (tmp_path / "outside.csv").write_text(CUTOFF_CSV, encoding="utf-8")
    (folder / "link.csv").symlink_to(tmp_path / "outside.csv")

    rows = read_csv_rows(folder)

    assert [r["exam"] for r in rows] == ["SSC CGL", "SSC CGL"]  # only a.csv


def test_read_csv_rows_missing_folder_is_empty(tmp_path):
    assert read_csv_rows(tmp_path / "nope") == []


def test_weightage_is_summed_per_topic_and_labelled_unverified_analysis():
    rows = import_weightage(list(csv.DictReader(io.StringIO(WEIGHT_CSV))))
    totals = {(w.subject, w.topic): w.weight for w in aggregate_weightage(rows)}
    assert totals == {("Quant", "Percentages"): 7.0, ("English", "Idioms"): 2.0}
    assert all(w.source == "analysis (unverified)" for w in aggregate_weightage(rows))


async def test_import_inbox_files_keeps_only_official_cutoffs(monkeypatch, tmp_path):
    (tmp_path / "cutoffs").mkdir()
    (tmp_path / "weightage").mkdir()
    (tmp_path / "cutoffs" / "a.csv").write_text(CUTOFF_CSV, encoding="utf-8")
    (tmp_path / "weightage" / "w.csv").write_text(WEIGHT_CSV, encoding="utf-8")
    stored = {}

    async def fake_store(session, cutoffs, weights):
        stored["cutoffs"], stored["weights"] = cutoffs, weights

    monkeypatch.setattr("techradar.exams.weights.store_imports", fake_store)
    n_cut, n_weight = await import_inbox_files(object(), tmp_path, frozenset({"ssc.gov.in"}))

    assert (n_cut, n_weight) == (1, 2)
    assert [c.score for c in stored["cutoffs"]] == [136.5]


@pytest.mark.db
async def test_store_imports_is_idempotent(session):
    cutoffs = import_cutoffs(
        list(csv.DictReader(io.StringIO(CUTOFF_CSV))), frozenset({"ssc.gov.in"})
    )
    weights = aggregate_weightage(import_weightage(list(csv.DictReader(io.StringIO(WEIGHT_CSV)))))
    await store_imports(session, cutoffs, weights)
    await store_imports(session, cutoffs, weights)  # the same files again change nothing
    n = (await session.execute(select(func.count()).select_from(Cutoff))).scalar()
    w = (
        await session.execute(
            select(TopicWeightRow.weight).where(TopicWeightRow.topic == "Percentages")
        )
    ).scalar_one()
    assert n >= 1 and w == 7.0


def test_gate_weights_empty():
    assert gate_weights([]) == []
