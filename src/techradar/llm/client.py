import re
from collections.abc import Sequence
from typing import Any, Protocol

import httpx
from pydantic import BaseModel, ValidationError

from techradar.llm.roles import Role, RoleModel

try:
    import litellm
    from litellm import Router
except ImportError:
    litellm = None  # type: ignore[assignment]
    Router = None  # type: ignore[assignment, misc]


class Completer(Protocol):
    """Protocol for LLM chat completion backends."""

    async def complete(
        self,
        role: Role,
        messages: list[dict[str, str]],
        *,
        json_schema: dict[str, Any],
        max_tokens: int,
        timeout_s: float,
    ) -> str: ...


class Embedder(Protocol):
    """Protocol for text embedding backends."""

    async def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class LLMOutputError(Exception):
    """Raised when LLM output fails schema validation after all retry attempts."""


def strip_thinking(text: str) -> str:
    """Strip <think>...</think> chain-of-thought blocks from model output."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


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
    """Request structured JSON completion conforming to schema, with retries on failure."""
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


class LiteLLMCompleter:
    """Completer backed by litellm.Router or direct Ollama HTTP fallback."""

    def __init__(self, roles: dict[Role, RoleModel], ollama_base_url: str) -> None:
        self.roles = roles
        self.ollama_base_url = ollama_base_url.rstrip("/")
        self._router: Any = None

        if Router is not None:
            model_list = [
                {
                    "model_name": role.value,
                    "litellm_params": {
                        "model": f"ollama_chat/{rm.ollama_tag}",
                        "api_base": self.ollama_base_url,
                        "num_ctx": rm.num_ctx,
                    },
                }
                for role, rm in roles.items()
            ]
            self._router = Router(model_list=model_list)

    async def complete(
        self,
        role: Role,
        messages: list[dict[str, str]],
        *,
        json_schema: dict[str, Any],
        max_tokens: int = 1024,
        timeout_s: float = 120.0,
    ) -> str:
        if self._router is not None:
            response = await self._router.acompletion(
                model=role.value,
                messages=messages,
                response_format={"type": "json_object", "response_schema": json_schema},
                max_tokens=max_tokens,
                timeout=timeout_s,
            )
            content: str = response.choices[0].message.content or ""
            return content

        # Direct Ollama API fallback when litellm is not installed
        role_model = self.roles.get(role)
        if role_model is None:
            raise ValueError(f"Role {role} not configured")

        async with httpx.AsyncClient(timeout=timeout_s) as client:
            resp = await client.post(
                f"{self.ollama_base_url}/api/chat",
                json={
                    "model": role_model.ollama_tag,
                    "messages": messages,
                    "format": json_schema,
                    "options": {
                        "num_ctx": role_model.num_ctx,
                        "num_predict": max_tokens,
                    },
                    "stream": False,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            content_val: str = data.get("message", {}).get("content", "")
            return content_val


class LiteLLMEmbedder:
    """Embedder backed by litellm.Router or direct Ollama HTTP fallback."""

    def __init__(self, roles: dict[Role, RoleModel], ollama_base_url: str) -> None:
        self.roles = roles
        self.ollama_base_url = ollama_base_url.rstrip("/")
        self._router: Any = None

        embed_model = roles.get(Role.EMBED)
        tag = embed_model.ollama_tag if embed_model else "bge-m3"

        if Router is not None:
            model_list = [
                {
                    "model_name": Role.EMBED.value,
                    "litellm_params": {
                        "model": f"ollama/{tag}",
                        "api_base": self.ollama_base_url,
                    },
                }
            ]
            self._router = Router(model_list=model_list)

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if self._router is not None:
            response = await self._router.aembedding(
                model=Role.EMBED.value,
                input=list(texts),
            )
            return [
                item["embedding"] if isinstance(item, dict) else item.embedding
                for item in response.data
            ]

        # Direct Ollama API fallback when litellm is not installed
        embed_model = self.roles.get(Role.EMBED)
        tag = embed_model.ollama_tag if embed_model else "bge-m3"

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{self.ollama_base_url}/api/embed",
                json={
                    "model": tag,
                    "input": list(texts),
                },
            )
            resp.raise_for_status()
            data = resp.json()
            embeddings: list[list[float]] = data.get("embeddings", [])
            return embeddings
