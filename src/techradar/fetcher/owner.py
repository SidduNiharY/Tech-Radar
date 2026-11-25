"""Owner links and files into the pipeline (Phase 3 Task 3).

`intake_link` (the worker's `owner_link` job) checks an owner's URL with `check_url` against
the Squid allowlist and inserts a `raw_items` row of the `manual` source (id 0, status `new`);
nothing is fetched here. The fetcher fetches it through Squid and checks every redirect again.

The bot saves a PDF or a pasted note as `<sha256>.<ext>` in `data/telegram-in` and defers the
`owner_file` job with that name. This moves it the way the fetcher stores a download: the file
is read without following links and must still hash to its name (`read_private`), copied into
`data/raw` under the same hash name, recorded as a `raw_items` row of the `manual` source (id 0,
status `fetched`), and handed to the parser sandbox as a `ParseJob` with origin `telegram`. The
Intake Gateway then runs every check (type, structure, antivirus, YARA, injection, links) in
the no-network parser. The drop-folder copy is removed only if it is still the inode read.

SEC: SEC-06, SEC-15, SEC-26, SEC-57.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Literal

import anyio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import RawItem
from techradar.fetcher.store import write_job
from techradar.intake.owner_files import UnsafeFile, read_private, remove_if_same, write_private
from techradar.schemas.pipeline import JobKind, ParseJob
from techradar.security.urls import UrlRejected, check_url

logger = logging.getLogger(__name__)

OWNER_SOURCE_ID = 0  # the seeded `manual` source (migration 0005)

NOT_ALLOWLISTED_REPLY = (
    "That site isn't on the allowlist. Add it to infra/squid/allowlist.txt on the server, "
    "or paste the text instead."
)
LINK_QUEUED_REPLY = "Queued. You'll see it in tomorrow's briefing or with /ask."
# Per extension: the job kind, the URL scheme the item is known by, and the byte limit.
_KINDS: dict[str, tuple[JobKind, str, int]] = {
    "pdf": ("pdf", "upload", 5_000_000),
    "html": ("page", "paste", 1_000_000),
}

OwnerOutcome = Literal["queued", "duplicate", "refused"]
OWNER_FILE_REPLIES: dict[str, str] = {
    "duplicate": "You sent that one before.",
    "refused": "Couldn't take that file.",
}


async def take_owner_file(
    session: AsyncSession,
    name: str,
    in_dir: Path,
    raw_dir: Path,
    jobs_dir: Path,
    *,
    now: datetime,
) -> OwnerOutcome:
    """Move one drop-folder file into raw/ and queue its parse job; commit the row first."""
    ext = name.rsplit(".", 1)[-1] if "." in name else ""
    spec = _KINDS.get(ext)
    if spec is None:
        logger.warning("owner file refused: not a pdf or html hash name")
        return "refused"
    kind, scheme, max_bytes = spec
    try:
        data, st = await anyio.to_thread.run_sync(read_private, in_dir, name, max_bytes)
    except UnsafeFile as exc:
        logger.warning("owner file refused: %s", exc)
        return "refused"

    sha = hashlib.sha256(data).hexdigest()
    url = f"{scheme}:{sha}"
    url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()
    known = (
        await session.execute(select(RawItem.id).where(RawItem.url_hash == url_hash))
    ).scalar_one_or_none()
    if known is not None:
        await anyio.to_thread.run_sync(remove_if_same, in_dir, name, st)
        return "duplicate"

    raw_ext: Literal["pdf", "html"] = "pdf" if kind == "pdf" else "html"
    raw_name = await anyio.to_thread.run_sync(write_private, raw_dir, data, raw_ext)
    row = RawItem(
        source_id=OWNER_SOURCE_ID,
        url=url,
        url_hash=url_hash,
        kind=kind,
        status="fetched",
        raw_name=raw_name,
        fetched_at=now,
    )
    session.add(row)
    await session.flush()
    raw_item_id = row.id
    await session.commit()  # the row is durable before the parser can produce a result

    job = ParseJob(
        job_id=uuid.uuid4().hex,
        kind=kind,
        raw_name=raw_name,
        url=url,
        source_id=OWNER_SOURCE_ID,
        raw_item_id=raw_item_id,
        origin="telegram",
    )
    await anyio.to_thread.run_sync(write_job, job, jobs_dir)
    await anyio.to_thread.run_sync(remove_if_same, in_dir, name, st)
    return "queued"


def link_reply(reason: str) -> str:
    if reason == "not_allowlisted":
        return NOT_ALLOWLISTED_REPLY
    return f"That link can't be used ({reason})."


async def intake_link(session: AsyncSession, url: str, allowed: frozenset[str]) -> str:
    """Check the link and queue it for the fetcher; return the reply for the owner.

    Runs in the worker (`owner_link` job). Nothing is fetched here; the fetcher fetches the
    row through Squid and re-checks every redirect against the same allowlist.
    """
    try:
        clean = check_url(url, allowed)
    except UrlRejected as exc:
        return link_reply(exc.reason)
    url_hash = hashlib.sha256(clean.encode("utf-8")).hexdigest()
    known = (
        await session.execute(select(RawItem.id).where(RawItem.url_hash == url_hash))
    ).scalar_one_or_none()
    if known is None:
        path = clean.split("?", 1)[0].lower()
        session.add(
            RawItem(
                source_id=OWNER_SOURCE_ID,
                url=clean,
                url_hash=url_hash,
                kind="pdf" if path.endswith(".pdf") else "page",
                status="new",
            )
        )
        await session.flush()
    return LINK_QUEUED_REPLY
