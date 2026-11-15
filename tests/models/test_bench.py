"""Tests for model bench scoring and role pass criteria."""

from pathlib import Path

import pytest
import yaml

from techradar.models.bench import (
    passes_checker,
    passes_embed,
    passes_night,
    passes_worker,
    score_bench_run,
)


def test_pass_lines() -> None:
    """Test standard pass line thresholds from Phase 10 / 03 spec."""
    assert passes_worker({"tag_agreement": 0.91, "json_first_try": 0.99})
    assert not passes_worker({"tag_agreement": 0.89, "json_first_try": 1.0})
    assert not passes_worker({"tag_agreement": 0.95, "json_first_try": 0.95})

    assert passes_checker({"wrong_key_catch": 0.92, "false_flag": 0.04})
    assert not passes_checker({"wrong_key_catch": 0.92, "false_flag": 0.06})
    assert not passes_checker({"wrong_key_catch": 0.85, "false_flag": 0.02})

    assert passes_night([True, True, False])
    assert not passes_night([True, False, False])
    assert passes_night([True, True, True])

    assert passes_embed({"hit_rate_at_5": 0.85, "mrr": 0.75})
    assert not passes_embed({"hit_rate_at_5": 0.75, "mrr": 0.75})


def test_score_bench_run_perfect() -> None:
    """Test 100% accuracy when all answers match."""
    expected = ["A", "B", "62", "C"]
    actual = ["A", "B", "62", "C"]
    res = score_bench_run(expected, actual)
    assert res.total == 4
    assert res.correct == 4
    assert res.accuracy == 1.0
    assert res.mismatches == []


def test_score_bench_run_partial() -> None:
    """Test partial accuracy with detected mismatch indices."""
    expected = ["A", "B", "C", "D"]
    actual = ["A", "X", "C", "Y"]
    res = score_bench_run(expected, actual)
    assert res.total == 4
    assert res.correct == 2
    assert res.accuracy == 0.5
    assert res.mismatches == [1, 3]


def test_score_bench_run_normalization() -> None:
    """Test case-insensitivity and whitespace stripping."""
    expected = [" A ", "QuickSort", "O(N^2)"]
    actual = ["a", " quicksort ", "o(n^2)"]
    res = score_bench_run(expected, actual)
    assert res.total == 3
    assert res.correct == 3
    assert res.accuracy == 1.0
    assert res.mismatches == []


def test_score_bench_run_empty() -> None:
    """Test empty sequences."""
    res = score_bench_run([], [])
    assert res.total == 0
    assert res.correct == 0
    assert res.accuracy == 0.0
    assert res.mismatches == []


def test_score_bench_run_length_mismatch() -> None:
    """Test ValueError when lengths differ."""
    with pytest.raises(ValueError, match="same length"):
        score_bench_run(["A", "B"], ["A"])


def test_score_bench_run_indian_languages() -> None:
    """Test that Indian language strings (Hindi, Telugu) pass through and match correctly."""
    expected = ["कलन विधि", "ఆపరేటింగ్ సిస్టమ్", "GATE परीक्षा 2026"]
    actual = [" कलन विधि ", "ఆపరేటింగ్ సిస్టమ్", "gate परीक्षा 2026"]
    res = score_bench_run(expected, actual)
    assert res.total == 3
    assert res.correct == 3
    assert res.accuracy == 1.0


def test_example_eval_set_validity() -> None:
    """Verify that evals/sets/gate_cs.example.yaml is valid YAML and matches the schema."""
    eval_file = Path(__file__).resolve().parents[2] / "evals" / "sets" / "gate_cs.example.yaml"
    assert eval_file.is_file(), f"Eval file missing: {eval_file}"

    data = yaml.safe_load(eval_file.read_text(encoding="utf-8"))
    assert data["version"] == 1
    assert data["suite"] == "gate_cs"
    items = data["items"]
    assert len(items) >= 5

    expected = [item["expected_answer"] for item in items]
    score = score_bench_run(expected, expected)
    assert score.accuracy == 1.0
