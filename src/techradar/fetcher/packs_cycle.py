"""The starter-pack step of the fetch loop (Phase 2c Task 9).

Reads `exam_packs.yaml` each cycle, mirrors it into the database, downloads the pending
items of approved packs (the only internet stage of packs) and links docs the intake
created from earlier downloads. With the seed file (nothing approved, no items) it makes
no HTTP call at all.

SEC: SEC-05, SEC-25, SEC-57.
"""

from __future__ import annotations

import dataclasses
import logging
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from techradar.fetcher.http import FetchDeps
from techradar.library.packs import download_pack_items, link_pack_docs, load_packs, sync_packs

log = logging.getLogger(__name__)

PACKS_FILES = (Path("/etc/techradar/exam_packs.yaml"), Path("infra/sources/exam_packs.yaml"))


def packs_file() -> Path | None:
    """The mounted file in the container, else the repo copy; None if neither exists."""
    return next((p for p in PACKS_FILES if p.is_file()), None)


async def run_pack_cycle(
    deps: FetchDeps,
    session_factory: Callable[..., AbstractAsyncContextManager[AsyncSession]],
    packs_path: Path | None,
    packs_dir: Path,
    pack_max_bytes: int,
) -> dict[str, int]:
    """One pass: load, sync, download, link. A malformed file stops the pass (logged)."""
    if packs_path is None:
        return {}
    try:
        packs = load_packs(packs_path, deps.allowed)
    except ValueError as exc:
        log.error("starter packs file refused: %s", exc)
        return {}
    pack_deps = dataclasses.replace(deps, max_bytes=pack_max_bytes)
    async with session_factory() as session:
        await sync_packs(session, packs)
        counts = await download_pack_items(pack_deps, session, packs, packs_dir)
        counts["linked"] = await link_pack_docs(session, packs_dir)
    return counts
