"""Core protocols and JSON completion client for LLM roles."""

import re
from collections.abc import Sequence
from typing import Any, Protocol

from pydantic import BaseModel, ValidationError

from techradar.llm.roles import Role

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


class Completer(Protocol):
    """Protocol for LLM chat completion backends."""

    async def complete(
        self,
        role: Role,
        messages: list[dict[str, str]],
        *,
        json_schema: dict[str, Any],
        max_tokens: int = 1024,
        timeout_s: float = 120.0,
    ) -> str: ...


class Embedder(Protocol):
    """Protocol for text embedding backends."""

    async def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class LLMOutputError(Exception):
    """Raised when LLM output fails schema validation after all retry attempts."""


def strip_thinking(text: str) -> str:
    """Remove reasoning tokens within <think>...</think> from response."""
    return _THINK_RE.sub("", text).strip()


async def complete_json[T: BaseModel](
    completer: Completer,
    role: Role,
    system: str,
    user: str,
    schema: type[T],
    *,
    max_tokens: int = 1024,
    timeout_s: float = 120.0,
    attempts: int = 2,
) -> T:
    """Send structured prompt to LLM and parse response against Pydantic schema."""
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    json_schema = schema.model_json_schema()

    last_error: Exception | None = None
    for _ in range(max(1, attempts)):
        raw = await completer.complete(
            role,
            messages,
            json_schema=json_schema,
            max_tokens=max_tokens,
            timeout_s=timeout_s,
        )
        cleaned = strip_thinking(raw)
        try:
            return schema.model_validate_json(cleaned)
        except (ValidationError, ValueError) as err:
            last_error = err
            continue

    raise LLMOutputError(
        f"Failed to obtain valid JSON matching {schema.__name__} after {attempts} attempts"
    ) from last_error
