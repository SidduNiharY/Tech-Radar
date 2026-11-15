from collections.abc import Sequence
from typing import Any

from techradar.llm.client import Completer, Embedder
from techradar.llm.roles import Role


class FakeCompleter(Completer):
    """Fake completer for deterministic testing without LLM inference."""

    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []
        self._index = 0

    async def complete(
        self,
        role: Role,
        messages: list[dict[str, str]],
        *,
        json_schema: dict[str, Any],
        max_tokens: int = 1024,
        timeout_s: float = 120.0,
    ) -> str:
        self.calls.append(
            {
                "role": role,
                "messages": messages,
                "json_schema": json_schema,
                "max_tokens": max_tokens,
                "timeout_s": timeout_s,
            }
        )
        if self._index >= len(self.responses):
            raise IndexError("FakeCompleter ran out of mock responses")
        resp = self.responses[self._index]
        self._index += 1
        return resp


class FakeEmbedder(Embedder):
    """Fake embedder returning predefined or deterministic vectors."""

    def __init__(
        self,
        dim: int = 4,
        table: dict[str, list[float]] | None = None,
    ) -> None:
        self.dim = dim
        self.table = table or {}
        self.calls: list[list[str]] = []

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        text_list = list(texts)
        self.calls.append(text_list)
        results: list[list[float]] = []
        for t in text_list:
            if t in self.table:
                results.append(self.table[t])
            else:
                results.append([0.0] * self.dim)
        return results


class FakeResolver:
    """Fake DNS resolver for testing SSRF / URL validation."""

    def __init__(
        self,
        ips: list[str] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.ips = ips or []
        self.error = error
        self.calls: list[str] = []

    async def resolve(self, host: str) -> list[str]:
        self.calls.append(host)
        if self.error is not None:
            raise self.error
        return list(self.ips)


class FakeClock:
    """Fake clock for deterministic rate limiter and timeout testing."""

    def __init__(self, start: float = 0.0) -> None:
        self.current = start
        self.slept: list[float] = []

    def now(self) -> float:
        return self.current

    async def sleep(self, s: float) -> None:
        self.slept.append(s)
        self.current += s


class FakeReranker:
    """Fake reranker for deterministic cross-encoder testing."""

    def __init__(
        self,
        scores: dict[str, float] | None = None,
        default: float = 0.5,
    ) -> None:
        self.scores = scores or {}
        self.default = default
        self.calls: list[tuple[str, list[str]]] = []

    def score(self, query: str, passages: Sequence[str]) -> list[float]:
        passage_list = list(passages)
        self.calls.append((query, passage_list))
        return [self.scores.get(p, self.default) for p in passage_list]


class FakeTranscriber:
    """Fake transcriber for deterministic testing without Whisper inference."""

    def __init__(self, transcript: Any | None = None) -> None:
        from techradar.voice.transcribe import Transcript

        self.transcript = transcript or Transcript(
            text="hello world", words=[], lang="en", duration_s=2.0
        )
        self.calls: list[Any] = []

    def transcribe(self, path: Any) -> Any:
        self.calls.append(path)
        return self.transcript


class FakePhonemeModel:
    """Fake wav2vec2 phoneme model for deterministic CTC alignment testing."""

    def __init__(self, prob: float = 0.8) -> None:
        import string

        self.prob = prob
        # Basic vocab with blank at 0 and ASCII letters
        self.blank_id = 0
        self.vocab: dict[str, int] = {"<pad>": 0}
        for i, c in enumerate(string.ascii_lowercase, start=1):
            self.vocab[c] = i
        self.calls: list[Any] = []

    def log_probs(self, wav: Any) -> Any:
        import math

        import numpy as np

        self.calls.append(wav)
        # Create at least 30 frames
        frames = max(30, int(len(wav) / 320))
        vocab_size = len(self.vocab)
        # Low background log prob
        log_prob = np.full((frames, vocab_size), math.log(1e-6), dtype=np.float32)
        # Assign self.prob to all valid symbols
        target_lp = math.log(max(self.prob, 1e-6))
        for token_id in self.vocab.values():
            log_prob[:, token_id] = target_lp
        return log_prob
