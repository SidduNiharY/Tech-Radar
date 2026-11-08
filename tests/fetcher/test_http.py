from __future__ import annotations

import httpx
import pytest
import respx

from techradar.fetcher.http import FetchDeps, fetch_url
from techradar.fetcher.limiter import DomainLimiter
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
        user_agent="TechRadarBrain/0.1 (personal, non-commercial)",
    )


@pytest.mark.asyncio
async def test_not_allowlisted_rejected_before_network(
    deps: FetchDeps, respx_mock: respx.MockRouter
):
    r = await fetch_url("https://evil.example/x", "page", deps)
    assert r.status == "rejected"
    assert not respx_mock.calls


@pytest.mark.asyncio
async def test_private_ip_resolved_rejected(deps: FetchDeps, respx_mock: respx.MockRouter):
    deps.resolver = FakeResolver(ips=["127.0.0.1"])
    r = await fetch_url("https://pib.gov.in/x", "page", deps)
    assert r.status == "rejected"
    assert r.reason == "private_address"
    assert not respx_mock.calls


@pytest.mark.asyncio
async def test_robots_disallow_skips(deps: FetchDeps, respx_mock: respx.MockRouter):
    async def fetch_robots(url: str) -> tuple[int, str]:
        return 200, "User-agent: *\nDisallow: /"

    deps.robots = RobotsCache(fetch_robots)
    r = await fetch_url("https://pib.gov.in/news", "page", deps)
    assert r.status == "robots"
    assert r.reason == "robots"
    assert not respx_mock.calls


@pytest.mark.asyncio
async def test_robots_5xx_fails_closed(deps: FetchDeps, respx_mock: respx.MockRouter):
    async def fetch_robots(url: str) -> tuple[int, str]:
        return 503, "Service Unavailable"

    deps.robots = RobotsCache(fetch_robots)
    r = await fetch_url("https://pib.gov.in/news", "page", deps)
    assert r.status == "robots"
    assert r.reason == "robots"
    assert not respx_mock.calls


@pytest.mark.asyncio
async def test_304_not_modified(deps: FetchDeps, respx_mock: respx.MockRouter):
    respx_mock.get("https://pib.gov.in/doc").mock(return_value=httpx.Response(304))
    r = await fetch_url("https://pib.gov.in/doc", "page", deps, etag="abc")
    assert r.status == "not_modified"


@pytest.mark.asyncio
async def test_content_length_too_large(deps: FetchDeps, respx_mock: respx.MockRouter):
    respx_mock.get("https://pib.gov.in/doc").mock(
        return_value=httpx.Response(
            200,
            headers={"Content-Length": "6000000", "Content-Type": "text/html"},
            text="",
        )
    )
    r = await fetch_url("https://pib.gov.in/doc", "page", deps)
    assert r.status == "too_large"


@pytest.mark.asyncio
async def test_streamed_body_too_large(deps: FetchDeps, respx_mock: respx.MockRouter):
    respx_mock.get("https://pib.gov.in/doc").mock(
        return_value=httpx.Response(
            200,
            headers={"Content-Type": "text/html"},
            content=b"x" * 5_000_001,
        )
    )
    r = await fetch_url("https://pib.gov.in/doc", "page", deps)
    assert r.status == "too_large"


@pytest.mark.asyncio
async def test_bad_content_type_rejected(deps: FetchDeps, respx_mock: respx.MockRouter):
    respx_mock.get("https://pib.gov.in/doc").mock(
        return_value=httpx.Response(
            200,
            headers={"Content-Type": "application/octet-stream"},
            content=b"plain bytes",
        )
    )
    r = await fetch_url("https://pib.gov.in/doc", "page", deps)
    assert r.status == "bad_type"
    assert r.reason == "application/octet-stream"


@pytest.mark.asyncio
async def test_redirect_to_other_domain_rejected(deps: FetchDeps, respx_mock: respx.MockRouter):
    respx_mock.get("https://pib.gov.in/from").mock(
        return_value=httpx.Response(
            302,
            headers={"Location": "https://evil.example/target"},
        )
    )
    r = await fetch_url("https://pib.gov.in/from", "page", deps)
    assert r.status == "rejected"
    assert r.reason == "not_allowlisted"


@pytest.mark.asyncio
async def test_redirect_chain_over_three_rejected(deps: FetchDeps, respx_mock: respx.MockRouter):
    respx_mock.get("https://pib.gov.in/hop1").mock(
        return_value=httpx.Response(302, headers={"Location": "https://pib.gov.in/hop2"})
    )
    respx_mock.get("https://pib.gov.in/hop2").mock(
        return_value=httpx.Response(302, headers={"Location": "https://pib.gov.in/hop3"})
    )
    respx_mock.get("https://pib.gov.in/hop3").mock(
        return_value=httpx.Response(302, headers={"Location": "https://pib.gov.in/hop4"})
    )
    respx_mock.get("https://pib.gov.in/hop4").mock(
        return_value=httpx.Response(302, headers={"Location": "https://pib.gov.in/hop5"})
    )

    r = await fetch_url("https://pib.gov.in/hop1", "page", deps)
    assert r.status == "rejected"
    assert r.reason == "too_many_redirects"


@pytest.mark.asyncio
async def test_successful_fetch_page(deps: FetchDeps, respx_mock: respx.MockRouter):
    respx_mock.get("https://pib.gov.in/article").mock(
        return_value=httpx.Response(
            200,
            headers={
                "Content-Type": "text/html; charset=utf-8",
                "ETag": '"etag123"',
                "Last-Modified": "Thu, 01 Jan 2026 00:00:00 GMT",
            },
            content=b"<html><body>Article</body></html>",
        )
    )
    r = await fetch_url("https://pib.gov.in/article", "page", deps)
    assert r.status == "new"
    assert r.final_url == "https://pib.gov.in/article"
    assert r.body == b"<html><body>Article</body></html>"
    assert r.content_type == "text/html"
    assert r.etag == '"etag123"'
    assert r.last_modified == "Thu, 01 Jan 2026 00:00:00 GMT"


@pytest.mark.asyncio
async def test_successful_fetch_feed(deps: FetchDeps, respx_mock: respx.MockRouter):
    respx_mock.get("https://pib.gov.in/feed.xml").mock(
        return_value=httpx.Response(
            200,
            headers={"Content-Type": "application/rss+xml"},
            content=b"<rss><channel><title>News</title></channel></rss>",
        )
    )
    r = await fetch_url("https://pib.gov.in/feed.xml", "feed", deps)
    assert r.status == "new"
    assert r.content_type == "application/rss+xml"
    assert r.body is not None and b"<rss>" in r.body


@pytest.mark.asyncio
async def test_successful_fetch_pdf(deps: FetchDeps, respx_mock: respx.MockRouter):
    respx_mock.get("https://pib.gov.in/report.pdf").mock(
        return_value=httpx.Response(
            200,
            headers={"Content-Type": "application/pdf"},
            content=b"%PDF-1.4 test content",
        )
    )
    r = await fetch_url("https://pib.gov.in/report.pdf", "pdf", deps)
    assert r.status == "new"
    assert r.content_type == "application/pdf"
    assert r.body == b"%PDF-1.4 test content"


@pytest.mark.asyncio
async def test_http_error_non_2xx(deps: FetchDeps, respx_mock: respx.MockRouter):
    respx_mock.get("https://pib.gov.in/not_found").mock(return_value=httpx.Response(404))
    r = await fetch_url("https://pib.gov.in/not_found", "page", deps)
    assert r.status == "http_error"
    assert r.reason == "404"
