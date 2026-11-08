"""Tests for RAG retrieval evaluation metrics (Phase 2b Task 7).

SEC: SEC-41.
"""

import pytest

from evals.rag.metrics import mrr, recall_at_k


def test_recall_and_mrr() -> None:
    assert recall_at_k(["a", "b", "c"], ["c"], k=5) == 1.0
    assert recall_at_k(["a"], ["z"]) == 0.0
    assert mrr(["a", "b", "c"], ["b"]) == pytest.approx(0.5)
    assert mrr(["a", "b", "c"], ["z"]) == 0.0
