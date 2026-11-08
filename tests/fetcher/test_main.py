from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest
import respx

from techradar.db.models import RawItem, Source
from techradar.fetcher.http import FetchDeps
from techradar.fetcher.limiter import DomainLimiter
from techradar.fetcher.main import run_cycle
from techradar.fetcher.robots import RobotsCache
from tests.fakes import FakeClock, FakeResolver

ALLOWED_DOMAINS = frozenset({"pib.gov.in", ".pib.gov.in"})


@pytest.fixture
def fake_clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def fake_resolver() -> FakeResolver:
    return FakeResolver(ips=["93.184.216.34"])


@pytest.fixture
def robots_allow_all() -> RobotsCache:
    async def fetch_robots(url: str) -> tuple[int, str]:
        return 404, ""

    return RobotsCache(fetch_robots)


@pytest.fixture
def deps(
    fake_clock: FakeClock,
    fake_resolver: FakeResolver,
    robots_allow_all: RobotsCache,
) -> FetchDeps:
    limiter = DomainLimiter(5.0, fake_clock)
    client = httpx.AsyncClient()
    return FetchDeps(
        client=client,
        limiter=limiter,
        robots=robots_allow_all,
        allowed=ALLOWED_DOMAINS,
        resolver=fake_resolver,
        max_bytes=5_000_000,
        user_agent="TechRadarBrain/0.1",
    )


@pytest.mark.asyncio
async def test_run_cycle_fetches_due_feeds_and_raw_items(
    deps: FetchDeps,
    respx_mock: respx.MockRouter,
    tmp_path: Path,
):
    raw_dir = tmp_path / "raw"
    jobs_dir = tmp_path / "jobs"
    now = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)

    # Mock feed response
    respx_mock.get("https://pib.gov.in/feed.xml").mock(
        return_value=httpx.Response(
            200,
            headers={"Content-Type": "application/rss+xml"},
            content=b"<rss><channel><title>Gov</title></channel></rss>",
        )
    )

    # Mock page response
    respx_mock.get("https://pib.gov.in/article1").mock(
        return_value=httpx.Response(
            200,
            headers={"Content-Type": "text/html"},
            content=b"<html><body>Article 1</body></html>",
        )
    )

    # Mock PDF response
    respx_mock.get("https://pib.gov.in/report.pdf").mock(
        return_value=httpx.Response(
            200,
            headers={"Content-Type": "application/pdf"},
            content=b"%PDF-1.4 PDF report",
        )
    )

    # Create mock Source and RawItems
    src = Source(
        id=1,
        name="PIB",
        kind="rss",
        url="https://pib.gov.in/feed.xml",
        host="pib.gov.in",
        section="india",
        trust_tier="official",
        interval_min=120,
        last_fetched_at=now - timedelta(hours=3),
        enabled=True,
    )

    item1 = RawItem(
        id=10,
        source_id=1,
        url="https://pib.gov.in/article1",
        url_hash="hash1",
        kind="page",
        status="new",
    )

    item2 = RawItem(
        id=11,
        source_id=1,
        url="https://pib.gov.in/report.pdf",
        url_hash="hash2",
        kind="pdf",
        status="new",
    )

    # Setup mock session
    session = AsyncMock()

    class MockScalarResult:
        def __init__(self, items):
            self._items = items

        def scalars(self):
            return self

        def all(self):
            return self._items

    session.execute.side_effect = [
        MockScalarResult([src]),
        MockScalarResult([item1, item2]),
    ]
    session.commit = AsyncMock()

    @asynccontextmanager
    async def mock_session_factory():
        yield session

    counts = await run_cycle(deps, mock_session_factory, raw_dir, jobs_dir, now)

    assert counts == {"feeds": 1, "pages": 2, "rejected": 0, "not_modified": 0}
    assert src.last_fetched_at == now
    assert item1.status == "fetched"
    assert item2.status == "fetched"
    assert session.commit.called

    job_files = list(jobs_dir.glob("*.job.json"))
    assert len(job_files) == 3
