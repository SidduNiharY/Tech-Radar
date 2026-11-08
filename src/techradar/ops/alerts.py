from __future__ import annotations

import asyncio
import functools
import inspect
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

ALERT_WINDOW: timedelta = timedelta(hours=6)


class AlertStore:
    """In-memory or stateful store for deduplicated alert history."""

    def __init__(self) -> None:
        self.history: dict[str, datetime] = {}
        self.enqueued: list[dict[str, Any]] = []

    def should_alert(self, key: str, now: datetime) -> bool:
        last = self.history.get(key)
        if last is None or (now - last) >= ALERT_WINDOW:
            self.history[key] = now
            return True
        return False

    def enqueue(self, owner_chat_id: int, key: str, text: str) -> None:
        self.enqueued.append(
            {
                "owner_chat_id": owner_chat_id,
                "key": key,
                "text": text,
            }
        )


_DEFAULT_ALERT_STORE = AlertStore()


async def raise_alert(
    store: AlertStore | None,
    owner_chat_id: int,
    key: str,
    text: str,
    now: datetime | None = None,
) -> bool:
    """Enqueue alert if not deduplicated within ALERT_WINDOW."""
    if store is None:
        store = _DEFAULT_ALERT_STORE
    current_time = now or datetime.now(UTC)

    if store.should_alert(key, current_time):
        store.enqueue(owner_chat_id, key, text)
        return True
    return False


def alert_on_failure(
    name: str,
    store: AlertStore | None = None,
    owner_chat_id: int = 0,
    now_fn: Callable[[], datetime] | None = None,
) -> Callable:
    """Decorator to catch exceptions, raise sanitised alert, and re-raise.

    Ensures that raw exception messages (which may contain API keys or secrets)
    are strictly omitted from the alert text.
    """

    def decorator(fn: Callable) -> Callable:
        if inspect.iscoroutinefunction(fn):

            @functools.wraps(fn)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                try:
                    return await fn(*args, **kwargs)
                except Exception as exc:
                    now = now_fn() if now_fn else datetime.now(UTC)
                    alert_text = f"⚠️ Job {name} failed: {type(exc).__name__}"
                    await raise_alert(
                        store,
                        owner_chat_id,
                        f"job:{name}",
                        alert_text,
                        now,
                    )
                    raise

            return async_wrapper
        else:

            @functools.wraps(fn)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                try:
                    return fn(*args, **kwargs)
                except Exception as exc:
                    now = now_fn() if now_fn else datetime.now(UTC)
                    alert_text = f"⚠️ Job {name} failed: {type(exc).__name__}"
                    # Run alert in event loop or schedule
                    try:
                        loop = asyncio.get_running_loop()
                        loop.create_task(
                            raise_alert(store, owner_chat_id, f"job:{name}", alert_text, now)
                        )
                    except RuntimeError:
                        asyncio.run(
                            raise_alert(store, owner_chat_id, f"job:{name}", alert_text, now)
                        )
                    raise

            return sync_wrapper

    return decorator
