"""Database fixtures for the `db`-marked pipeline tests.

They need the Postgres from `compose.dev.yaml` (127.0.0.1:55432, migrations
applied) and the role passwords in ./secrets, so they run on the server only.

Pipeline code commits through its own sessions, so the pipeline tables are
emptied before and after each test that uses `pipeline_db`. That wipe only runs
when TR_DB_TESTS_MAY_WIPE=1 (set by `make test-db`); never run these tests
against a database that holds real notes.
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from techradar.db.engine import make_engine
from techradar.db.models import Fact, FactSource, Item, QuarantineItem, RawItem, Source
from techradar.pipeline.process import PipelineDeps
from techradar.settings import Settings
from tests.fakes import FakeCompleter, FakeEmbedder

PIPELINE_TABLES = (
    "fact_changes",
    "fact_sources",
    "facts",
    "notes",
    "items",
    "raw_items",
    "fetch_runs",
    "intake_log",
    "quarantine_items",
    "sources",
)
OFFICIAL = frozenset({"rbi.org.in"})


@dataclass
class FactsHolder:
    old: int
    new_official: int
    new_from_news_only: int
    older_official: int
    repeat_of_old_value: int


@pytest.fixture
def db_settings(tmp_path: Path) -> Settings:
    return Settings(
        telegram_owner_chat_id=1,
        db_host="127.0.0.1",
        db_port=55432,
        db_name="techradar",
        secrets_dir=Path("secrets"),
        data_dir=tmp_path / "data",
    )


async def _wipe(settings: Settings) -> None:
    engine = make_engine("migrator", settings)
    tables = ", ".join(f"techradar.{t}" for t in PIPELINE_TABLES)
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    await engine.dispose()


@pytest.fixture
async def pipeline_db(db_settings: Settings) -> AsyncGenerator[None]:
    if os.environ.get("TR_DB_TESTS_MAY_WIPE") != "1":
        pytest.skip("set TR_DB_TESTS_MAY_WIPE=1 (make test-db does) to allow wiping test tables")
    await _wipe(db_settings)
    yield
    await _wipe(db_settings)


@pytest.fixture
async def session(db_settings: Settings) -> AsyncGenerator[AsyncSession]:
    """A session whose changes are rolled back after the test."""
    engine = make_engine("app", db_settings)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s
        await s.rollback()
    await engine.dispose()


async def _source_item(session: AsyncSession, domain: str, n: int) -> Item:
    src = Source(
        name=f"test-{domain}-{n}",
        url=f"https://{domain}/feed-{n}.xml",
        host=domain,
        section="economy",
        trust_tier="official" if domain in OFFICIAL else "news",
    )
    session.add(src)
    await session.flush()
    raw = RawItem(
        source_id=src.id,
        url=f"https://{domain}/story-{n}",
        url_hash=f"{n:064d}",
        kind="page",
    )
    session.add(raw)
    await session.flush()
    item = Item(
        raw_item_id=raw.id,
        title=f"Story {n}",
        url=raw.url,
        domain=domain,
        lang="en",
        content_hash=f"{n:064x}",
    )
    session.add(item)
    await session.flush()
    return item


async def _fact(session: AsyncSession, n: int, value: str, as_of: date, domain: str) -> int:
    item = await _source_item(session, domain, n)
    fact = Fact(
        fact_key=f"test-fact-{n}",
        statement=f"Repo rate is {value}.",
        subject="repo rate",
        subject_key="rbi.repo_rate",
        value=value,
        section="economy",
        status="verified",
        source_count=1,
        as_of=as_of,
    )
    session.add(fact)
    await session.flush()
    session.add(FactSource(fact_id=fact.id, item_id=item.id, domain=domain, supported=True))
    await session.flush()
    return fact.id


@pytest.fixture
async def facts(session: AsyncSession) -> FactsHolder:
    """A realistic history of the repo rate (rolled back with `session`)."""
    return FactsHolder(
        older_official=await _fact(session, 1, "6.0%", date(2026, 1, 1), "rbi.org.in"),
        old=await _fact(session, 2, "5.5%", date(2026, 6, 1), "rbi.org.in"),
        repeat_of_old_value=await _fact(session, 3, "5.5%", date(2026, 9, 1), "rbi.org.in"),
        new_official=await _fact(session, 4, "5.25%", date(2026, 10, 1), "rbi.org.in"),
        new_from_news_only=await _fact(session, 5, "5.0%", date(2026, 10, 2), "thehindu.com"),
    )


@pytest.fixture
def deps(pipeline_db: None, db_settings: Settings, tmp_path: Path) -> PipelineDeps:
    """Pipeline deps on the real database, with fake models."""
    vault, clean, jobs, raw = (tmp_path / d for d in ("vault", "clean", "parse-jobs", "raw"))
    for d in (vault, clean, jobs, raw, db_settings.data_dir / "quarantine"):
        d.mkdir(parents=True, exist_ok=True)
    engine = make_engine("app", db_settings)
    return PipelineDeps(
        session_factory=async_sessionmaker(engine, expire_on_commit=False),
        completer=FakeCompleter([]),
        embedder=FakeEmbedder(dim=4),
        settings=db_settings,
        vault_root=vault,
        clean_dir=clean,
        jobs_dir=jobs,
        raw_dir=raw,
        allowed=frozenset({"rbi.org.in", "pib.gov.in"}),
        official=OFFICIAL,
    )


@pytest.fixture
async def finished_rows_8_days_old(deps: PipelineDeps) -> None:
    """A written item whose raw and clean files are 8 days old."""
    old = datetime.now(UTC) - timedelta(days=8)
    (deps.raw_dir / "old.html").write_text("<p>old</p>", encoding="utf-8")
    text_path = deps.clean_dir / "old.result.json"
    text_path.write_text("{}", encoding="utf-8")
    for p in (deps.raw_dir / "old.html", text_path):
        os.utime(p, (old.timestamp(), old.timestamp()))
    async with deps.session_factory() as s:
        item = await _source_item(s, "rbi.org.in", 90)
        raw = await s.get(RawItem, item.raw_item_id)
        assert raw is not None
        raw.status, raw.fetched_at, raw.raw_name = "done", old, "old.html"
        item.status, item.processed_at, item.text_path = "written", old, str(text_path)
        await s.commit()


@pytest.fixture
async def quarantined_item_8_days_old(deps: PipelineDeps) -> None:
    """A quarantined file whose 7-day hold has expired."""
    qdir = deps.settings.data_dir / "quarantine"
    qfile = qdir / "bad.pdf"
    qfile.write_bytes(b"%PDF-1.7 fake")
    old = datetime.now(UTC) - timedelta(days=8)
    async with deps.session_factory() as s:
        s.add(
            QuarantineItem(
                job_id="q" * 32,
                path=str(qfile),
                origin="fetch",
                reasons=["pdf_javascript"],
                created_at=old,
                expires_at=old + timedelta(days=7),
            )
        )
        await s.commit()
