"""Cross-encoder reranker for RAG hybrid retrieval (Phase 2b Task 4).

SEC: SEC-23, SEC-41.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class Reranker(Protocol):
    """Protocol for scoring query-passage pairs."""

    def score(self, query: str, passages: Sequence[str]) -> list[float]:
        """Score passages against query, returning values in [0, 1]."""
        ...


def sigmoid(x: float) -> float:
    """Logistic sigmoid function bounded to avoid overflow."""
    clipped = max(-500.0, min(500.0, float(x)))
    return 1.0 / (1.0 + math.exp(-clipped))


class CrossEncoderReranker:
    """Reranker using a local Hugging Face CrossEncoder model on CPU/CUDA."""

    def __init__(self, path: Path, device: str = "cpu") -> None:
        from sentence_transformers import CrossEncoder

        self.model = CrossEncoder(str(path), device=device)

    def score(self, query: str, passages: Sequence[str]) -> list[float]:
        if not passages:
            return []
        pairs = [[query, p] for p in passages]
        raw_scores = self.model.predict(pairs)
        return [sigmoid(s) for s in raw_scores]
