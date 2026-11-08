"""System status collection and health verification."""

import shutil
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path

import httpx
from sqlalchemy import text

from techradar.db.engine import make_engine
from techradar.settings import get_settings


@dataclass
class SystemStatus:
    """Snapshot of overall system health."""

    version: str = "0.1.0"
    db_ok: bool = False
    ollama_ok: bool = False
    loaded_models: list[str] = field(default_factory=list)
    disk_free_pct: float = 0.0


async def collect_status(
    check_db: Callable[[], Awaitable[bool]],
    check_ollama: Callable[[], Awaitable[list[str] | None]],
    check_disk: Callable[[], float],
    version: str = "0.1.0",
) -> SystemStatus:
    """Collect system status using injectable check functions."""
    db_ok = await check_db()
    models = await check_ollama()
    ollama_ok = models is not None
    loaded_models = models if models is not None else []
    disk_free_pct = check_disk()

    return SystemStatus(
        version=version,
        db_ok=db_ok,
        ollama_ok=ollama_ok,
        loaded_models=loaded_models,
        disk_free_pct=disk_free_pct,
    )


async def check_db_live() -> bool:
    """Probe PostgreSQL with a simple SELECT 1."""
    try:
        engine = make_engine("reader")
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT 1"))
            return result.scalar() == 1
    except Exception:
        return False


async def check_ollama_live(timeout_s: float = 5.0) -> list[str] | None:
    """Probe Ollama /api/ps endpoint for running models."""
    settings = get_settings()
    url = f"{settings.ollama_base_url.rstrip('/')}/api/ps"
    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return None
            data = resp.json()
            models_list = data.get("models", [])
            return [str(m.get("name")) for m in models_list if m.get("name")]
    except Exception:
        return None


def check_disk_live(data_dir: Path | None = None) -> float:
    """Compute free disk space percentage for data directory."""
    target = data_dir or get_settings().data_dir
    try:
        usage = shutil.disk_usage(target)
        if usage.total == 0:
            return 0.0
        return (usage.free / usage.total) * 100.0
    except Exception:
        return 0.0
