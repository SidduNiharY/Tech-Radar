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
