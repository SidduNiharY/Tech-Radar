from __future__ import annotations

import pytest

from techradar.exams.weights import (
    CutoffRow,
    PyqRow,
    TopicWeight,
    gate_weights,
    import_cutoffs,
    import_weightage,
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


def test_gate_weights_empty():
    assert gate_weights([]) == []
