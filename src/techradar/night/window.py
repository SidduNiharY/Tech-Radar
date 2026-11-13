from __future__ import annotations

import functools
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from techradar.ops.gpu import free_gpu

log = logging.getLogger(__name__)

Defer = Callable[[datetime, dict[str, Any]], Awaitable[None]]
Free = Callable[[], Awaitable[object]]


def in_night_window(now_local: datetime, start: time, end: time) -> bool:
    """True from start (inclusive) to end (exclusive); the window may cross midnight."""
    t = now_local.time().replace(tzinfo=None)
    if start <= end:
        return start <= t < end
    return t >= start or t < end


def next_window_start(now_local: datetime, start: time) -> datetime:
    """The next time the window opens, strictly after now_local."""
    candidate = now_local.replace(hour=start.hour, minute=start.minute, second=0, microsecond=0)
    if candidate <= now_local:
        candidate += timedelta(days=1)
    return candidate


def _parse_hhmm(value: str) -> time:
    h, m = value.split(":")
    return time(int(h), int(m))


def _utc_now() -> datetime:
    return datetime.now(UTC)


async def _default_free() -> list[str]:
    from techradar.settings import get_settings

    async with httpx.AsyncClient(timeout=30) as client:
        return await free_gpu(client, get_settings().ollama_base_url)


def _default_defer(task_name: str) -> Defer:
    async def defer(when: datetime, kwargs: dict[str, Any]) -> None:
        from techradar.worker.app import app

        await app.configure_task(name=task_name, schedule_at=when).defer_async(**kwargs)

    return defer


def night_only(
    fn: Callable[..., Awaitable[Any]] | None = None,
    *,
    task_name: str | None = None,
    defer: Defer | None = None,
    free: Free | None = None,
    now: Callable[[], datetime] | None = None,
    start: time | None = None,
    end: time | None = None,
    tz: str | None = None,
) -> Any:
    """Run an async job only inside the night window.

    Outside it, the same job (same keyword arguments) is deferred to the next window
    start and nothing runs. Inside it, the GPU is freed first. Use it under the task
    decorator, `@app.task` on top, with the job taking keyword arguments. Every option
    can be injected for tests; the defaults come from settings and the worker app.

    `task_name` is the exact procrastinate task name and is required unless `defer` is
    injected: a wrong name would defer a job that no worker runs. A failure while freeing
    the GPU is logged and the job still runs.
    """
    if defer is None and task_name is None:
        raise ValueError("night_only needs task_name when the default defer is used")

    def decorate(f: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        @functools.wraps(f)
        async def wrapper(**kwargs: Any) -> Any:
            if start is None or end is None or tz is None:
                from techradar.settings import get_settings

                s = get_settings()
                win = (_parse_hhmm(s.night_start), _parse_hhmm(s.night_end), s.tz)
            else:
                win = (start, end, tz)
            zone = ZoneInfo(win[2])
            now_local = (now or _utc_now)().astimezone(zone)
            if not in_night_window(now_local, win[0], win[1]):
                run_defer = defer or _default_defer(str(task_name))
                await run_defer(next_window_start(now_local, win[0]), kwargs)
                return None
            try:
                await (free or _default_free)()
            except (httpx.HTTPError, OSError) as exc:
                log.warning("could not free the GPU before the night job: %s", exc)
            return await f(**kwargs)

        return wrapper

    return decorate(fn) if fn is not None else decorate
