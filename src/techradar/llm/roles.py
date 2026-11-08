from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field


class Role(StrEnum):
    WORKER = "worker"
    CHECKER = "checker"
    NIGHT = "night"
    EMBED = "embed"
    VISION = "vision"


class RoleModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ollama_tag: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]*(:[a-z0-9._-]+)?$")
    family: str
    num_ctx: int = Field(ge=1024, le=32768)
    think: bool = False
    provider: Literal["ollama"] = "ollama"


class RoleConfigError(ValueError):
    """Raised when roles YAML configuration is invalid or missing required roles."""


def load_roles(path: Path, *, allow_cloud: bool = False) -> dict[Role, RoleModel]:
    """Load, validate, and return the model roles configuration from a YAML file.

    Enforces:
    - All 5 roles (worker, checker, night, embed, vision) must be defined.
    - Worker and checker models must not belong to the same family.
    - Providers must be 'ollama' unless allow_cloud is True.
    """
    if not path.is_file():
        raise RoleConfigError(f"missing roles file at path: {path}")

    raw: Any = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise RoleConfigError("roles file must contain a YAML mapping")

    # Check for missing roles
    for role in Role:
        if role.value not in raw:
            raise RoleConfigError(f"missing role: {role.value}")

    # Check provider restrictions
    if not allow_cloud:
        for role_name, conf in raw.items():
            if isinstance(conf, dict) and conf.get("provider", "ollama") != "ollama":
                raise RoleConfigError(
                    f"provider '{conf.get('provider')}' for role '{role_name}' "
                    "not permitted when allow_cloud is False"
                )

    # Validate schema for all roles
    roles: dict[Role, RoleModel] = {}
    for role in Role:
        roles[role] = RoleModel.model_validate(raw[role.value])

    # Validate independent worker/checker model family rule
    if roles[Role.WORKER].family == roles[Role.CHECKER].family:
        family = roles[Role.WORKER].family
        raise RoleConfigError(
            f"family conflict: worker and checker cannot share family ('{family}')"
        )

    return roles
