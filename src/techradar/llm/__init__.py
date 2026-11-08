"""TechRadar LLM package."""

from techradar.llm.client import (
    Completer,
    Embedder,
    LLMOutputError,
    complete_json,
    strip_thinking,
)
from techradar.llm.litellm import (
    LiteLLMCompleter,
    LiteLLMEmbedder,
)
from techradar.llm.roles import Role, RoleConfigError, RoleModel, load_roles

__all__ = [
    "Completer",
    "Embedder",
    "LLMOutputError",
    "LiteLLMCompleter",
    "LiteLLMEmbedder",
    "Role",
    "RoleConfigError",
    "RoleModel",
    "complete_json",
    "load_roles",
    "strip_thinking",
]
