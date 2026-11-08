"""LiteLLM and direct Ollama implementations of Completer and Embedder."""

from collections.abc import Sequence
from typing import Any

import httpx

from techradar.llm.client import Completer, Embedder
from techradar.llm.roles import Role, RoleModel

try:
    import litellm
    from litellm import Router
except ImportError:
    litellm = None  # type: ignore[assignment]
    Router = None  # type: ignore[assignment, misc]


class LiteLLMCompleter(Completer):
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
            return data.get("message", {}).get("content", "")


class LiteLLMEmbedder(Embedder):
    """Embedder backed by litellm.embedding or direct Ollama HTTP fallback."""

    def __init__(self, roles: dict[Role, RoleModel], ollama_base_url: str) -> None:
        self.roles = roles
        self.ollama_base_url = ollama_base_url.rstrip("/")

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []

        embed_model = self.roles.get(Role.EMBED)
        tag = embed_model.ollama_tag if embed_model else "bge-m3"

        if litellm is not None:
            response = await litellm.aembedding(
                model=f"ollama/{tag}",
                api_base=self.ollama_base_url,
                input=list(texts),
            )
            return [
                item["embedding"] if isinstance(item, dict) else item.embedding
                for item in response.data
            ]

        # Direct Ollama API fallback when litellm is not installed
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
