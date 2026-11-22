"""`/packs`: starter packs, their items and approved/blocked state (Phase 2c Task 9).

Owner's own chat only (the router already refuses others; checked again here). Read-only:
the bot never approves a pack or adds a URL; that is the owner's edit of
`infra/sources/exam_packs.yaml` after checking each URL in a browser (SEC-05).

SEC: SEC-05, SEC-26.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Any

from techradar.library.packs import pack_statuses, render_packs


async def packs_reply(
    chat_id: int,
    owner_id: int,
    session_factory: Callable[[], AbstractAsyncContextManager[Any]] | None,
) -> str | None:
    """The reply text, or None for any chat that is not the owner's."""
    if chat_id != owner_id:
        return None
    if session_factory is None:
        return "Not available yet."
    async with session_factory() as session:
        return render_packs(await pack_statuses(session))
