"""Failure alerts for jobs (Phase 5 Task 6). SEC-14, SEC-32.

An alert names the job and the exception type only, never the message: an exception message
can carry a URL, a path or a key. At most one alert per key every 6 hours, kept in Postgres
so a restart or a catch-up run after downtime never sends the same alert twice.
"""

from __future__ import annotations

import functools
import inspect
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from techradar.db.engine import make_session_factory
from techradar.db.models import JobAlert
from techradar.messaging.outbox import enqueue_message
from techradar.settings import get_settings

logger = logging.getLogger(__name__)

ALERT_WINDOW: timedelta = timedelta(hours=6)
ALERT_PURPOSE = "alert"


async def raise_alert(
    session: AsyncSession,
    owner_chat_id: int,
    key: str,
    text: str,
    now: datetime,
) -> bool:
    """Enqueue `text` to the owner unless `key` already alerted within ALERT_WINDOW.

    Returns whether a message was enqueued. The caller commits.
    """
    row = await session.get(JobAlert, key)
    if row is not None and (now - row.last_at) < ALERT_WINDOW:
        return False
    if row is None:
        session.add(JobAlert(key=key, last_at=now))
    else:
        row.last_at = now
    await enqueue_message(session, chat_id=owner_chat_id, text=text, purpose=ALERT_PURPOSE)
    await session.flush()
    return True


def failure_text(name: str, exc: BaseException) -> str:
    """`⚠️ Job <name> failed: <ExceptionType>`: never the exception message."""
    return f"⚠️ Job {name} failed: {type(exc).__name__}"


def alert_on_failure(
    name: str,
    *,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    owner_chat_id: int | None = None,
    now_fn: Callable[[], datetime] | None = None,
) -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]:
    """Decorator for async jobs: on an exception raise a de-duplicated alert, then re-raise.

    The alert uses its own session, so a job that failed in the database still reports.
    A failure to alert is logged (without the message) and never hides the job's exception.
    """

    def decorator(fn: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        if not inspect.iscoroutinefunction(fn):
            raise TypeError("alert_on_failure wraps async jobs only")

        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return await fn(*args, **kwargs)
            except Exception as exc:
                try:
                    settings = get_settings()
                    factory = session_factory or make_session_factory("app", settings)
                    owner = owner_chat_id or settings.telegram_owner_chat_id
                    now = now_fn() if now_fn else datetime.now(UTC)
                    async with factory() as session:
                        await raise_alert(
                            session, owner, f"job:{name}", failure_text(name, exc), now
                        )
                        await session.commit()
                except Exception as alert_exc:
                    logger.warning(
                        "could not raise the alert for job %s: %s", name, type(alert_exc).__name__
                    )
                raise

        return wrapper

    return decorator
