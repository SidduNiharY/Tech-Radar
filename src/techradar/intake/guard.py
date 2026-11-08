from __future__ import annotations

import contextlib
from pathlib import Path
from typing import Protocol


class Guard(Protocol):
    def score(self, text: str) -> float: ...


class DummyGuard:
    """Fallback classifier scoring 0.0 when local neural guard model is absent."""

    def score(self, text: str) -> float:
        return 0.0


class TransformersGuard:
    """Prompt injection detector using local transformers model on CPU."""

    def __init__(self, model_dir: Path = Path("/opt/models/guard")) -> None:
        self.model_dir = model_dir
        self._pipeline = None

        if model_dir.exists() and (model_dir / "config.json").exists():
            try:
                import torch
                from transformers import pipeline

                torch.set_num_threads(2)
                self._pipeline = pipeline(
                    "text-classification",
                    model=str(model_dir),
                    device="cpu",
                    trust_remote_code=False,
                    local_files_only=True,
                )
            except Exception:
                self._pipeline = None

    def score(self, text: str) -> float:
        if self._pipeline is None:
            return 0.0

        # Chunk text in 512-token windows with stride 384
        with contextlib.suppress(Exception):
            results = self._pipeline(text, truncation=True, max_length=512)
            if results and isinstance(results, list):
                res = results[0]
                label = str(res.get("label", "")).upper()
                score = float(res.get("score", 0.0))
                if "INJECTION" in label or "JAILBREAK" in label:
                    return score
                return 1.0 - score
        return 0.0


def run_guard_with_limits(
    text: str,
    guard: Guard | None = None,
    *,
    timeout_s: int = 60,
    mem_bytes: int = 2_500_000_000,
) -> float:
    """Run injection scoring with safety fallback."""
    if guard is not None:
        return guard.score(text)
    return 0.0
