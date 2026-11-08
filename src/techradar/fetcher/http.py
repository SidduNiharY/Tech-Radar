from __future__ import annotations

import asyncio
import socket
import urllib.parse
from dataclasses import dataclass
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field

from techradar.fetcher.limiter import DomainLimiter
from techradar.fetcher.robots import RobotsCache
from techradar.schemas.pipeline import JobKind
from techradar.security.urls import Resolver, UrlRejected, check_resolved, check_url

FetchStatus = Literal[
    "new",
    "not_modified",
    "too_large",
    "bad_type",
    "rejected",
    "robots",
    "http_error",
]


class FetchResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: FetchStatus
    final_url: str | None = None
    body: bytes | None = Field(default=None, repr=False)
    content_type: str | None = None
    etag: str | None = None
    last_modified: str | None = None
    reason: str | None = None


ALLOWED_TYPES: dict[JobKind, frozenset[str]] = {
    "feed": frozenset(
        {
            "application/rss+xml",
            "application/atom+xml",
            "application/xml",
            "text/xml",
        }
    ),
    "page": frozenset({"text/html"}),
    "pdf": frozenset({"application/pdf"}),
}


class SystemResolver:
    """Default DNS resolver using asyncio getaddrinfo."""

    async def resolve(self, host: str) -> list[str]:
        loop = asyncio.get_running_loop()
        try:
            addr_info = await loop.getaddrinfo(host, 443)
            return [info[4][0] for info in addr_info if info[4]]
        except (socket.gaierror, OSError) as exc:
            raise OSError(str(exc)) from exc


@dataclass
class FetchDeps:
    client: httpx.AsyncClient
    limiter: DomainLimiter
    robots: RobotsCache
    allowed: frozenset[str]
    resolver: Resolver
    max_bytes: int = 5_000_000
    user_agent: str = "TechRadarBrain/0.1 (personal, non-commercial)"


async def fetch_url(
    url: str,
    kind: JobKind,
    deps: FetchDeps,
    *,
    etag: str | None = None,
    last_modified: str | None = None,
) -> FetchResult:
    """Fetch URL adhering to security, rate limiting, and size boundaries."""
    # 1. check_url
    try:
        curr_url = check_url(url, deps.allowed)
    except UrlRejected as e:
        return FetchResult(status="rejected", reason=e.reason)

    # 2. check_resolved
    parsed = urllib.parse.urlsplit(curr_url)
    host = parsed.hostname or ""
    try:
        await check_resolved(host, deps.resolver)
    except UrlRejected as e:
        return FetchResult(status="rejected", reason=e.reason)

    # 3. robots.allowed
    if not await deps.robots.allowed(curr_url):
        return FetchResult(status="robots", reason="robots")

    # 4. limiter.wait
    await deps.limiter.wait(host)

    # 5. GET with follow_redirects=False, at most 3 redirects
    headers = {"User-Agent": deps.user_agent}
    if etag is not None:
        headers["If-None-Match"] = etag
    if last_modified is not None:
        headers["If-Modified-Since"] = last_modified

    redirect_count = 0
    while True:
        try:
            req = deps.client.build_request("GET", curr_url, headers=headers)
            resp = await deps.client.send(req, stream=True, follow_redirects=False)
        except httpx.RequestError as exc:
            return FetchResult(status="http_error", reason=str(exc))

        if resp.status_code in (301, 302, 303, 307, 308):
            redirect_count += 1
            if redirect_count > 3:
                await resp.aclose()
                return FetchResult(status="rejected", reason="too_many_redirects")

            location = resp.headers.get("location")
            await resp.aclose()
            if not location:
                return FetchResult(status="http_error", reason="redirect_missing_location")

            next_url = urllib.parse.urljoin(curr_url, location)
            try:
                curr_url = check_url(next_url, deps.allowed)
            except UrlRejected as e:
                return FetchResult(status="rejected", reason=e.reason)

            next_parsed = urllib.parse.urlsplit(curr_url)
            next_host = next_parsed.hostname or ""
            try:
                await check_resolved(next_host, deps.resolver)
            except UrlRejected as e:
                return FetchResult(status="rejected", reason=e.reason)

            await deps.limiter.wait(next_host)
            headers = {"User-Agent": deps.user_agent}
            continue

        # 6. 304 -> not_modified; non-2xx -> http_error
        if resp.status_code == 304:
            await resp.aclose()
            return FetchResult(status="not_modified", final_url=curr_url)

        if resp.status_code < 200 or resp.status_code >= 300:
            code_str = str(resp.status_code)
            await resp.aclose()
            return FetchResult(status="http_error", final_url=curr_url, reason=code_str)

        # 7. Content-Type stripped must be in ALLOWED_TYPES[kind]
        raw_ctype = resp.headers.get("content-type", "")
        ctype = raw_ctype.split(";")[0].strip().lower()
        allowed_types = ALLOWED_TYPES.get(kind, frozenset())
        if ctype not in allowed_types:
            await resp.aclose()
            return FetchResult(status="bad_type", final_url=curr_url, reason=ctype or raw_ctype)

        # 8. Content-Length header > max_bytes or streamed body > max_bytes -> too_large
        cl_header = resp.headers.get("content-length")
        if cl_header:
            try:
                if int(cl_header) > deps.max_bytes:
                    await resp.aclose()
                    return FetchResult(status="too_large", final_url=curr_url)
            except ValueError:
                pass

        body_chunks: list[bytes] = []
        received = 0
        try:
            async for chunk in resp.aiter_bytes():
                received += len(chunk)
                if received > deps.max_bytes:
                    return FetchResult(status="too_large", final_url=curr_url)
                body_chunks.append(chunk)
        finally:
            await resp.aclose()

        body = b"".join(body_chunks)

        return FetchResult(
            status="new",
            final_url=curr_url,
            body=body,
            content_type=ctype,
            etag=resp.headers.get("etag"),
            last_modified=resp.headers.get("last-modified"),
        )
