from __future__ import annotations

import pytest

from techradar.fetcher.limiter import DomainLimiter
from techradar.fetcher.robots import RobotsCache
from tests.fakes import FakeClock


@pytest.mark.asyncio
async def test_limiter_waits_between_same_host():
    clock = FakeClock()
    lim = DomainLimiter(5.0, clock)
    await lim.wait("pib.gov.in")
    await lim.wait("pib.gov.in")
    assert clock.slept == [5.0]


@pytest.mark.asyncio
async def test_limiter_different_hosts_no_wait():
    clock = FakeClock()
    lim = DomainLimiter(5.0, clock)
    await lim.wait("pib.gov.in")
    await lim.wait("other.org")
    assert clock.slept == []


@pytest.mark.asyncio
async def test_limiter_case_insensitive():
    clock = FakeClock()
    lim = DomainLimiter(5.0, clock)
    await lim.wait("PIB.GOV.IN")
    await lim.wait("pib.gov.in")
    assert clock.slept == [5.0]


@pytest.mark.asyncio
async def test_limiter_elapsed_time_subtracted():
    clock = FakeClock()
    lim = DomainLimiter(5.0, clock)
    await lim.wait("pib.gov.in")
    clock.current += 2.0
    await lim.wait("pib.gov.in")
    assert clock.slept == [3.0]


@pytest.mark.asyncio
async def test_robots_cache_200_allowed_and_disallowed():
    clock = FakeClock()
    calls: list[str] = []

    async def mock_fetch(url: str) -> tuple[int, str]:
        calls.append(url)
        return 200, "User-agent: *\nDisallow: /admin\nAllow: /admin/public"

    robots = RobotsCache(mock_fetch, clock=clock)
    assert await robots.allowed("https://pib.gov.in/admin") is False
    assert await robots.allowed("https://pib.gov.in/admin/public") is True
    assert await robots.allowed("https://pib.gov.in/news") is True
    assert calls == ["https://pib.gov.in/robots.txt"]


@pytest.mark.asyncio
async def test_robots_cache_404_allows():
    calls: list[str] = []

    async def mock_fetch(url: str) -> tuple[int, str]:
        calls.append(url)
        return 404, ""

    robots = RobotsCache(mock_fetch)
    assert await robots.allowed("https://example.org/anything") is True
    assert await robots.allowed("https://example.org/other") is True
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_robots_cache_410_allows():
    calls: list[str] = []

    async def mock_fetch(url: str) -> tuple[int, str]:
        calls.append(url)
        return 410, ""

    robots = RobotsCache(mock_fetch)
    assert await robots.allowed("https://example.org/anything") is True
    assert await robots.allowed("https://example.org/other") is True
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_robots_cache_5xx_fails_closed():
    calls: list[str] = []

    async def mock_fetch(url: str) -> tuple[int, str]:
        calls.append(url)
        return 503, "Service Unavailable"

    robots = RobotsCache(mock_fetch)
    assert await robots.allowed("https://example.org/anything") is False
    assert await robots.allowed("https://example.org/other") is False
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_robots_cache_exception_fails_closed():
    calls: list[str] = []

    async def mock_fetch(url: str) -> tuple[int, str]:
        calls.append(url)
        raise ConnectionError("network unreachable")

    robots = RobotsCache(mock_fetch)
    assert await robots.allowed("https://example.org/anything") is False
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_robots_invalid_url_denies():
    async def mock_fetch(url: str) -> tuple[int, str]:
        return 200, ""

    robots = RobotsCache(mock_fetch)
    assert await robots.allowed("invalid-no-scheme") is False
