from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from techradar.db.engine import make_engine
from techradar.db.models import RawItem, Source
from techradar.fetcher.due import SourceRow, due_sources
from techradar.fetcher.http import FetchDeps, SystemResolver, fetch_url
from techradar.fetcher.limiter import DomainLimiter, SystemClock
from techradar.fetcher.robots import RobotsCache
from techradar.fetcher.store import store_raw, write_job
from techradar.schemas.pipeline import JobKind, ParseJob
from techradar.security.urls import load_allowlist
from techradar.settings import get_settings


async def run_cycle(
    deps: FetchDeps,
    session_factory: Callable[..., AbstractAsyncContextManager[AsyncSession]],
    raw_dir: Path,
    jobs_dir: Path,
    now: datetime,
) -> dict[str, int]:
    """Execute one fetch cycle for due feeds and pending raw items."""
    counts = {"feeds": 0, "pages": 0, "rejected": 0, "not_modified": 0}

    async with session_factory() as session:
        # 1. Fetch due feeds
        src_stmt = select(Source).where(Source.enabled == True)  # noqa: E712
        src_res = await session.execute(src_stmt)
        sources = list(src_res.scalars().all())

        rows = [
            SourceRow(
                id=s.id,
                url=s.url,
                interval_min=s.interval_min,
                last_fetched_at=s.last_fetched_at,
                enabled=s.enabled,
            )
            for s in sources
        ]
        due = due_sources(rows, now)
        source_map = {s.id: s for s in sources}

        for row in due:
            src = source_map[row.id]
            fetch_res = await fetch_url(
                src.url,
                "feed",
                deps,
                etag=src.etag,
                last_modified=src.last_modified,
            )
            src.last_fetched_at = now
            if fetch_res.status == "new" and fetch_res.body is not None:
                raw_name = store_raw(fetch_res.body, raw_dir, "xml")
                src.etag = fetch_res.etag
                src.last_modified = fetch_res.last_modified
                job_id = uuid.uuid4().hex
                job = ParseJob(
                    job_id=job_id,
                    kind="feed",
                    raw_name=raw_name,
                    url=fetch_res.final_url or src.url,
                    source_id=src.id,
                    origin="fetch",
                )
                write_job(job, jobs_dir)
                counts["feeds"] += 1
            elif fetch_res.status == "not_modified":
                counts["not_modified"] += 1
            else:
                counts["rejected"] += 1

        # 2. Fetch up to 50 raw_items with status new
        raw_stmt = select(RawItem).where(RawItem.status == "new").order_by(RawItem.id).limit(50)
        raw_res = await session.execute(raw_stmt)
        raw_items = list(raw_res.scalars().all())

        for item in raw_items:
            clean_url = item.url.lower().split("?")[0]
            is_pdf = clean_url.endswith(".pdf")
            kind: JobKind = "pdf" if is_pdf else "page"
            ext: Literal["pdf", "html"] = "pdf" if is_pdf else "html"

            fetch_res = await fetch_url(item.url, kind, deps)
            item.fetched_at = now
            if fetch_res.status == "new" and fetch_res.body is not None:
                raw_name = store_raw(fetch_res.body, raw_dir, ext)
                item.status = "fetched"
                item.raw_name = raw_name
                job_id = uuid.uuid4().hex
                job = ParseJob(
                    job_id=job_id,
                    kind=kind,
                    raw_name=raw_name,
                    url=fetch_res.final_url or item.url,
                    source_id=item.source_id,
                    raw_item_id=item.id,
                    origin="fetch",
                )
                write_job(job, jobs_dir)
                counts["pages"] += 1
            elif fetch_res.status == "not_modified":
                counts["not_modified"] += 1
            else:
                item.status = "rejected"
                item.reject_reason = fetch_res.reason or fetch_res.status
                counts["rejected"] += 1

        await session.commit()

    return counts


async def _run_fetcher(
    allowed: frozenset[str],
    settings: Any,
    raw_dir: Path,
    jobs_dir: Path,
) -> None:
    engine = make_engine("app", settings)
    session_factory: Any = async_sessionmaker(engine, expire_on_commit=False)

    clock = SystemClock()
    limiter = DomainLimiter(settings.per_domain_delay_s, clock)
    resolver = SystemResolver()

    async with httpx.AsyncClient(
        proxy=settings.https_proxy,
        timeout=settings.fetch_timeout_s,
        trust_env=False,
    ) as client:

        async def fetch_robots(robots_url: str) -> tuple[int, str]:
            resp = await client.get(
                robots_url,
                headers={"User-Agent": settings.user_agent},
                follow_redirects=True,
            )
            return resp.status_code, resp.text

        robots = RobotsCache(fetch_robots, ua_token="TechRadarBrain")  # noqa: S106
        deps = FetchDeps(
            client=client,
            limiter=limiter,
            robots=robots,
            allowed=allowed,
            resolver=resolver,
            max_bytes=settings.max_fetch_bytes,
            user_agent=settings.user_agent,
        )

        while True:
            now = datetime.now(UTC)
            try:
                counts = await run_cycle(deps, session_factory, raw_dir, jobs_dir, now)
                print(f"Fetch cycle complete: {counts}")
            except Exception as exc:
                print(f"Error in fetch cycle: {exc}")
            await asyncio.sleep(60)


def main() -> None:
    settings = get_settings()
    allowlist_path = Path("infra/squid/allowlist.txt")
    allowed = load_allowlist(allowlist_path) if allowlist_path.is_file() else frozenset()

    raw_dir = settings.data_dir / "raw"
    jobs_dir = settings.data_dir / "parse-jobs"
    raw_dir.mkdir(parents=True, exist_ok=True)
    jobs_dir.mkdir(parents=True, exist_ok=True)

    asyncio.run(_run_fetcher(allowed, settings, raw_dir, jobs_dir))


if __name__ == "__main__":
    main()
