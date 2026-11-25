"""Owner files from the bot's drop folder into raw/ and the parser queue (Phase 3 Task 3).

SEC: SEC-05, SEC-06, SEC-15, SEC-26, SEC-57.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import respx
from sqlalchemy import select

from techradar.fetcher.http import FetchDeps, fetch_url
from techradar.fetcher.limiter import DomainLimiter
from techradar.fetcher.owner import take_owner_file
from techradar.fetcher.robots import RobotsCache
from techradar.intake.owner_files import write_private
from techradar.schemas.pipeline import ParseJob
from tests.fakes import FakeClock, FakeResolver

NOW = datetime(2026, 11, 25, 6, 0, tzinfo=UTC)
PDF = b"%PDF-1.7\n" + b"x" * 300
ALLOWED = frozenset({"pib.gov.in", ".pib.gov.in"})


def _fake_session(known: int | None = None) -> MagicMock:
    session = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = known
    session.execute = AsyncMock(return_value=result)
    added: list[Any] = []

    def add(row: Any) -> None:
        added.append(row)

    async def flush() -> None:
        for row in added:
            row.id = 17

    session.add.side_effect = add
    session.flush = AsyncMock(side_effect=flush)
    session.commit = AsyncMock()
    session.added = added
    return session


def _dirs(tmp_path: Path) -> tuple[Path, Path, Path]:
    return tmp_path / "telegram-in", tmp_path / "raw", tmp_path / "parse-jobs"


async def test_owner_pdf_becomes_a_raw_file_and_a_telegram_parse_job(tmp_path: Path) -> None:
    in_dir, raw_dir, jobs_dir = _dirs(tmp_path)
    name = write_private(in_dir, PDF, "pdf")
    session = _fake_session()
    outcome = await take_owner_file(session, name, in_dir, raw_dir, jobs_dir, now=NOW)
    assert outcome == "queued"
    assert (raw_dir / name).read_bytes() == PDF
    assert (raw_dir / name).stat().st_mode & 0o777 == 0o640
    assert list(in_dir.iterdir()) == []  # the drop copy is gone
    (job_file,) = list(jobs_dir.glob("*.job.json"))
    job = ParseJob.model_validate(json.loads(job_file.read_text()))
    sha = name.split(".")[0]
    assert (job.kind, job.origin, job.source_id, job.raw_item_id) == ("pdf", "telegram", 0, 17)
    assert job.raw_name == name and job.url == f"upload:{sha}"
    (row,) = session.added
    assert (row.source_id, row.status, row.kind, row.raw_name) == (0, "fetched", "pdf", name)
    assert row.url_hash == hashlib.sha256(f"upload:{sha}".encode()).hexdigest()
    session.commit.assert_awaited()


async def test_owner_paste_becomes_a_page_job(tmp_path: Path) -> None:
    in_dir, raw_dir, jobs_dir = _dirs(tmp_path)
    name = write_private(in_dir, b"<html><body><p>note</p></body></html>", "html")
    assert await take_owner_file(_fake_session(), name, in_dir, raw_dir, jobs_dir, now=NOW) == (
        "queued"
    )
    (job_file,) = list(jobs_dir.glob("*.job.json"))
    job = ParseJob.model_validate_json(job_file.read_text())
    assert job.kind == "page" and job.url.startswith("paste:") and job.origin == "telegram"


async def test_duplicate_owner_file_is_not_queued_again(tmp_path: Path) -> None:
    in_dir, raw_dir, jobs_dir = _dirs(tmp_path)
    name = write_private(in_dir, PDF, "pdf")
    session = _fake_session(known=5)
    assert await take_owner_file(session, name, in_dir, raw_dir, jobs_dir, now=NOW) == ("duplicate")
    assert not jobs_dir.exists() and session.added == [] and list(in_dir.iterdir()) == []


@pytest.mark.parametrize(
    "name", ["../raw/x.pdf", "/etc/passwd", "a" * 64 + ".exe", "a" * 64 + ".ogg", "x"]
)
async def test_a_name_that_is_not_a_drop_folder_hash_name_is_refused(
    tmp_path: Path, name: str
) -> None:
    in_dir, raw_dir, jobs_dir = _dirs(tmp_path)
    in_dir.mkdir()
    session = _fake_session()
    assert await take_owner_file(session, name, in_dir, raw_dir, jobs_dir, now=NOW) == "refused"
    assert not raw_dir.exists() and not jobs_dir.exists()
    session.execute.assert_not_called()


async def test_symlink_planted_in_the_drop_folder_is_refused(tmp_path: Path) -> None:
    in_dir, raw_dir, jobs_dir = _dirs(tmp_path)
    in_dir.mkdir()
    secret = tmp_path / "secret.pdf"
    secret.write_bytes(PDF)
    name = hashlib.sha256(PDF).hexdigest() + ".pdf"
    (in_dir / name).symlink_to(secret)
    session = _fake_session()
    assert await take_owner_file(session, name, in_dir, raw_dir, jobs_dir, now=NOW) == "refused"
    assert not raw_dir.exists() and not jobs_dir.exists()
    assert secret.exists() and (in_dir / name).is_symlink()  # nothing removed through it


async def test_swapped_content_is_refused(tmp_path: Path) -> None:
    in_dir, raw_dir, jobs_dir = _dirs(tmp_path)
    in_dir.mkdir()
    name = hashlib.sha256(PDF).hexdigest() + ".pdf"
    (in_dir / name).write_bytes(b"%PDF-1.7 something else")
    assert await take_owner_file(_fake_session(), name, in_dir, raw_dir, jobs_dir, now=NOW) == (
        "refused"
    )
    assert not jobs_dir.exists()


async def test_oversized_drop_file_is_refused(tmp_path: Path) -> None:
    in_dir, raw_dir, jobs_dir = _dirs(tmp_path)
    name = write_private(in_dir, b"%PDF-" + b"x" * 5_000_001, "pdf")
    assert await take_owner_file(_fake_session(), name, in_dir, raw_dir, jobs_dir, now=NOW) == (
        "refused"
    )
    assert not jobs_dir.exists()


async def test_symlink_planted_in_raw_is_never_written_through(tmp_path: Path) -> None:
    in_dir, raw_dir, jobs_dir = _dirs(tmp_path)
    name = write_private(in_dir, PDF, "pdf")
    raw_dir.mkdir()
    victim = tmp_path / "victim"
    victim.write_text("keep")
    (raw_dir / name).symlink_to(victim)
    session = _fake_session()
    with pytest.raises(Exception, match="another file"):
        await take_owner_file(session, name, in_dir, raw_dir, jobs_dir, now=NOW)
    assert victim.read_text() == "keep" and not jobs_dir.exists() and session.added == []


async def test_drop_folder_that_is_a_symlink_is_refused(tmp_path: Path) -> None:
    real = tmp_path / "real"
    name = write_private(real, PDF, "pdf")
    in_dir, raw_dir, jobs_dir = _dirs(tmp_path)
    os.symlink(real, in_dir)
    assert await take_owner_file(_fake_session(), name, in_dir, raw_dir, jobs_dir, now=NOW) == (
        "refused"
    )
    assert (real / name).exists()


# --- an owner link is fetched only through the fetcher's checks ------------------------------


@pytest.fixture
def deps() -> FetchDeps:
    async def no_robots(url: str) -> tuple[int, str]:
        return 404, ""

    return FetchDeps(
        client=httpx.AsyncClient(),
        limiter=DomainLimiter(0.0, FakeClock()),
        robots=RobotsCache(no_robots),
        allowed=ALLOWED,
        resolver=FakeResolver(ips=["93.184.216.34"]),
    )


@pytest.mark.parametrize(
    "location",
    [
        "https://evil.example/x",
        "http://pib.gov.in/plain",
        "https://127.0.0.1/admin",
        "https://[::1]/admin",
        "file:///etc/passwd",
        "javascript:alert(1)",
        "https://pib.gov.in:8443/x",
    ],
)
async def test_owner_link_redirect_off_the_allowlist_is_refused(
    deps: FetchDeps, respx_mock: respx.MockRouter, location: str
) -> None:
    respx_mock.get("https://pib.gov.in/owner").mock(
        return_value=httpx.Response(302, headers={"Location": location})
    )
    r = await fetch_url("https://pib.gov.in/owner", "page", deps)
    assert r.status == "rejected" and r.body is None
    assert len(respx_mock.calls) == 1  # the redirect target is never requested


async def test_owner_link_to_a_host_resolving_private_is_refused(
    respx_mock: respx.MockRouter,
) -> None:
    async def no_robots(url: str) -> tuple[int, str]:
        return 404, ""

    deps = FetchDeps(
        client=httpx.AsyncClient(),
        limiter=DomainLimiter(0.0, FakeClock()),
        robots=RobotsCache(no_robots),
        allowed=ALLOWED,
        resolver=FakeResolver(ips=["10.0.0.5"]),
    )
    r = await fetch_url("https://pib.gov.in/x", "page", deps)
    assert r.status == "rejected" and r.reason == "private_address"
    assert not respx_mock.calls


# --- database (run on the server) ------------------------------------------------------------


@pytest.mark.db
async def test_owner_file_row_is_source_zero_and_fetched(session: Any, tmp_path: Path) -> None:
    from techradar.db.models import RawItem

    in_dir, raw_dir, jobs_dir = _dirs(tmp_path)
    data = PDF + tmp_path.name.encode()  # unique per run
    name = write_private(in_dir, data, "pdf")
    assert await take_owner_file(session, name, in_dir, raw_dir, jobs_dir, now=NOW) == "queued"
    sha = name.split(".")[0]
    row = (
        await session.execute(select(RawItem).where(RawItem.url == f"upload:{sha}"))
    ).scalar_one()
    assert (row.source_id, row.status, row.kind, row.raw_name) == (0, "fetched", "pdf", name)
    # The same PDF again is a duplicate, not a second row or job.
    write_private(in_dir, data, "pdf")
    assert await take_owner_file(session, name, in_dir, raw_dir, jobs_dir, now=NOW) == ("duplicate")
    assert len(list(jobs_dir.glob("*.job.json"))) == 1
    await session.delete(row)
    await session.commit()


@pytest.mark.db
async def test_owner_link_redirected_off_the_allowlist_is_rejected_by_the_fetch_cycle(
    session: Any, tmp_path: Path, respx_mock: respx.MockRouter, monkeypatch: pytest.MonkeyPatch
) -> None:
    from contextlib import asynccontextmanager

    from techradar.db.models import RawItem, Source
    from techradar.fetcher.main import run_cycle

    url = f"https://pib.gov.in/owner-{tmp_path.name}"
    row = RawItem(
        source_id=0,
        url=url,
        url_hash=hashlib.sha256(url.encode()).hexdigest(),
        kind="page",
        status="new",
    )
    session.add(row)
    await session.flush()
    respx_mock.get(url).mock(
        return_value=httpx.Response(302, headers={"Location": "https://evil.example/x"})
    )
    # run_cycle commits; here it only flushes, so the fixture rolls everything back.
    monkeypatch.setattr(session, "commit", session.flush)
    # Only this test's row: no feed is due and no other new raw item is picked up.
    sources = (await session.execute(select(Source).where(Source.enabled.is_(True)))).scalars()
    for s in sources:
        s.last_fetched_at = NOW
    others = (
        await session.execute(select(RawItem).where(RawItem.status == "new", RawItem.id != row.id))
    ).scalars()
    for o in others:
        o.status = "held_by_test"

    @asynccontextmanager
    async def factory():
        yield session

    async def no_robots(u: str) -> tuple[int, str]:
        return 404, ""

    deps = FetchDeps(
        client=httpx.AsyncClient(),
        limiter=DomainLimiter(0.0, FakeClock()),
        robots=RobotsCache(no_robots),
        allowed=ALLOWED,
        resolver=FakeResolver(ips=["93.184.216.34"]),
    )
    raw_dir, jobs_dir = tmp_path / "raw", tmp_path / "jobs"
    await run_cycle(deps, factory, raw_dir, jobs_dir, NOW)
    await session.refresh(row)
    assert row.status == "rejected" and row.reject_reason == "not_allowlisted"
    assert not jobs_dir.exists() or list(jobs_dir.iterdir()) == []
