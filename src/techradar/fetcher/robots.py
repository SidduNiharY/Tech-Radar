from __future__ import annotations

import asyncio
import time
import urllib.parse
import urllib.robotparser
from collections.abc import Awaitable, Callable
from typing import Literal

from techradar.fetcher.limiter import Clock


class RobotsCache:
    """Robots.txt cache with RFC-compliant fail-closed behavior."""

    def __init__(
        self,
        fetch_text: Callable[[str], Awaitable[tuple[int, str]]],
        ua_token: str = "TechRadarBrain",  # noqa: S107
        ttl_s: int = 86400,
        clock: Clock | None = None,
    ) -> None:
        self.fetch_text = fetch_text
        self.ua_token = ua_token
        self.ttl_s = ttl_s
        self.clock = clock
        self._cache: dict[
            str,
            tuple[Literal["parser", "bool"], urllib.robotparser.RobotFileParser | bool, float],
        ] = {}
        self._lock = asyncio.Lock()

    def _now(self) -> float:
        if self.clock is not None:
            return self.clock.now()
        return time.monotonic()

    async def allowed(self, url: str) -> bool:
        parsed = urllib.parse.urlsplit(url)
        if not parsed.scheme or not parsed.netloc:
            return False
        origin = f"{parsed.scheme}://{parsed.netloc}"
        robots_url = f"{origin}/robots.txt"

        async with self._lock:
            now = self._now()
            cached = self._cache.get(origin)
            if cached is not None:
                kind, val, expires_at = cached
                if now < expires_at:
                    if kind == "parser" and isinstance(val, urllib.robotparser.RobotFileParser):
                        return val.can_fetch(self.ua_token, url)
                    return bool(val)

            # Fetch robots.txt
            try:
                status, text = await self.fetch_text(robots_url)
            except Exception:
                self._cache[origin] = ("bool", False, now + 3600.0)
                return False

            if status == 200:
                rp = urllib.robotparser.RobotFileParser()
                rp.parse(text.splitlines())
                self._cache[origin] = ("parser", rp, now + self.ttl_s)
                return rp.can_fetch(self.ua_token, url)
            if status in (404, 410):
                self._cache[origin] = ("bool", True, now + self.ttl_s)
                return True

            # Any other status code: deny for 3600s
            self._cache[origin] = ("bool", False, now + 3600.0)
            return False
