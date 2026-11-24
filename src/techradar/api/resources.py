"""Connections the API opens on first use and closes when it stops.

- Sessions as `tr_app` for routes that change data, and as `tr_ro` for `GET` routes, so a
  `GET` cannot write even by mistake (SEC-54: GET never changes data).
- A Procrastinate app (as `tr_app`) to defer jobs by name; the API imports no job code.
- Ollama's `/api/ps` and `/proc/meminfo` for the Models screen, read without the proxy.

Nothing connects or reads a secret until a route needs it, so building the app (tests, the
OpenAPI export) touches no database.
"""

from __future__ import annotations

import asyncio
import json
import logging
import urllib.request
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path
from typing import Any

from procrastinate import App, PsycopgConnector
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from techradar.db.engine import DbRole, make_session_factory
from techradar.settings import Settings, read_secret

logger = logging.getLogger(__name__)

Defer = Callable[[str, Mapping[str, Any]], Awaitable[None]]
OLLAMA_TIMEOUT_S = 3.0
MAX_PS_BYTES = 256_000
MEMINFO = Path("/proc/meminfo")


class Resources:
    """Lazily built connections, one set per app."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._factories: dict[DbRole, async_sessionmaker[AsyncSession]] = {}
        self._queue: App | None = None
        self._lock = asyncio.Lock()

    def session_factory(self, role: DbRole) -> async_sessionmaker[AsyncSession]:
        if role not in self._factories:
            self._factories[role] = make_session_factory(role, self.settings)
        return self._factories[role]

    async def queue(self) -> App:
        async with self._lock:
            if self._queue is None:
                s = self.settings
                connector = PsycopgConnector(
                    kwargs={
                        "host": s.db_host,
                        "port": s.db_port,
                        "dbname": s.db_name,
                        "user": "tr_app",
                        "password": read_secret("tr_app_password", s.secrets_dir),
                    },
                    min_size=1,
                    max_size=2,
                )
                app = App(connector=connector)
                await app.open_async()
                self._queue = app
            return self._queue

    async def defer(self, task_name: str, args: Mapping[str, Any]) -> None:
        """Queue a job by name with keyword arguments (the worker owns the code)."""
        queue = await self.queue()
        await queue.configure_task(name=task_name).defer_async(**dict(args))

    async def aclose(self) -> None:
        if self._queue is not None:
            await self._queue.close_async()
            self._queue = None
        for factory in self._factories.values():
            bind = factory.kw.get("bind")
            if bind is not None:
                await bind.dispose()
        self._factories.clear()


# --- Ollama and memory ------------------------------------------------------------------


def parse_ollama_ps(payload: object) -> list[dict[str, Any]]:
    """`{"models": [{"name", "size", "size_vram"}, ...]}` to plain rows; junk is skipped."""
    rows: list[dict[str, Any]] = []
    models = payload.get("models") if isinstance(payload, dict) else None
    if not isinstance(models, list):
        return rows
    for m in models[:50]:
        if not isinstance(m, dict):
            continue
        name, size, vram = m.get("name"), m.get("size"), m.get("size_vram", 0)
        if not isinstance(name, str) or not name or len(name) > 200:
            continue
        if not all(isinstance(v, int) and not isinstance(v, bool) and v >= 0 for v in (size, vram)):
            continue
        rows.append({"name": name, "size_bytes": size, "size_vram_bytes": vram})
    return rows


def _fetch_ps(url: str) -> object:
    # No proxy: Ollama is on the internal `llm` network, never behind Squid.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(url, timeout=OLLAMA_TIMEOUT_S) as resp:  # noqa: S310 (fixed http URL)
        return json.loads(resp.read(MAX_PS_BYTES + 1)[:MAX_PS_BYTES])


async def ollama_ps(base_url: str) -> list[dict[str, Any]]:
    """Loaded models, or [] when Ollama does not answer (the screen then shows none)."""
    if not base_url.startswith("http://"):
        return []
    try:
        payload = await asyncio.to_thread(_fetch_ps, base_url.rstrip("/") + "/api/ps")
    except Exception:  # unreachable, slow, or not JSON: show nothing loaded
        logger.info("ollama /api/ps unavailable")
        return []
    return parse_ollama_ps(payload)


def parse_meminfo(text: str) -> tuple[int, int]:
    """(MemTotal, MemAvailable) in bytes from /proc/meminfo; 0 for a missing line."""
    found: dict[str, int] = {}
    for line in text.splitlines():
        key, _, rest = line.partition(":")
        parts = rest.split()
        if key in ("MemTotal", "MemAvailable") and parts and parts[0].isdigit():
            found[key] = int(parts[0]) * 1024
    return found.get("MemTotal", 0), found.get("MemAvailable", 0)


def read_meminfo(path: Path = MEMINFO) -> tuple[int, int]:
    try:
        return parse_meminfo(path.read_text(encoding="ascii", errors="replace")[:20_000])
    except OSError:
        return 0, 0
