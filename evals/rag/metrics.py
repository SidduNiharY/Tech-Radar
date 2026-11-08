"""Metrics for RAG retrieval evaluation (Phase 2b Task 7).

SEC: SEC-41.
"""

from __future__ import annotations

from collections.abc import Sequence


def recall_at_k(ranked: Sequence[str], expected: Sequence[str], k: int = 5) -> float:
    """Calculate recall@k for ranked results against expected documents."""
    if not expected:
        return 1.0
    top_k = set(ranked[:k])
    found = sum(1 for e in expected if e in top_k)
    return float(found / len(expected))


def mrr(ranked: Sequence[str], expected: Sequence[str]) -> float:
    """Calculate Mean Reciprocal Rank (MRR) of the first expected document."""
    expected_set = set(expected)
    for rank, item in enumerate(ranked, start=1):
        if item in expected_set:
            return 1.0 / rank
    return 0.0
