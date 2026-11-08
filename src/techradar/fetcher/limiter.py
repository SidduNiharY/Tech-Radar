from __future__ import annotations

import asyncio
import time
from typing import Protocol


class Clock(Protocol):
    def now(self) -> float: ...
    async def sleep(self, s: float) -> None: ...


class SystemClock:
    """Real system clock using time.monotonic and asyncio.sleep."""

    def now(self) -> float:
        return time.monotonic()

    async def sleep(self, s: float) -> None:
        await asyncio.sleep(s)


class DomainLimiter:
    """Per-host rate limiter ensuring a minimum interval between requests."""

    def __init__(self, min_interval_s: float, clock: Clock) -> None:
        self.min_interval_s = min_interval_s
        self.clock = clock
        self._last_times: dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def wait(self, host: str) -> None:
        async with self._lock:
            key = host.lower()
            now = self.clock.now()
            last = self._last_times.get(key)
            if last is not None:
                elapsed = now - last
                if elapsed < self.min_interval_s:
                    to_sleep = self.min_interval_s - elapsed
                    await self.clock.sleep(to_sleep)
            self._last_times[key] = self.clock.now()
