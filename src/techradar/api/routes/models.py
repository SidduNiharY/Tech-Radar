"""`GET /v1/models/status`: which model does which job, what is loaded, host memory.

Read-only. Sources: roles.yaml, Ollama's `/api/ps` (no proxy, 3 s timeout, nothing loaded
when it does not answer) and `/proc/meminfo`.
"""

from __future__ import annotations

from fastapi import APIRouter

from techradar.api.deps import LoadedModels, Memory, Roles
from techradar.api.schemas import LoadedModel, ModelsStatus

router = APIRouter(prefix="/models", tags=["models"])


@router.get("/status", response_model=ModelsStatus)
async def models_status(roles: Roles, loaded: LoadedModels, memory: Memory) -> ModelsStatus:
    total, available = memory
    return ModelsStatus(
        roles=roles,
        loaded=[LoadedModel.model_validate(m) for m in loaded],
        ram_total_bytes=total,
        ram_available_bytes=available,
    )
