"""Database fixtures for the `db`-marked pipeline tests.

They need the Postgres from `compose.dev.yaml` (127.0.0.1:55432, migrations
applied) and the role passwords in ./secrets, so they run on the server only.

Pipeline code commits through its own sessions, so the pipeline tables are
emptied before and after each test that uses `pipeline_db`. That wipe only runs
when TR_DB_TESTS_MAY_WIPE=1 (set by `make test-db`); never run these tests
against a database that holds real notes.
"""

from __future__ import annotations

import json
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
from techradar.llm.client import Completer
from techradar.pipeline.process import PipelineDeps
from techradar.schemas.pipeline import CleanDoc, FeedEntry, IntakeStep, IntakeVerdict, ParseResult
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
ALLOWED = frozenset({"rbi.org.in", "pib.gov.in"})

# One story, as two newspapers might publish it.
STORY_TITLE = "RBI keeps the repo rate at 5.5%"
STORY_TEXT = "The Reserve Bank of India kept the repo rate at 5.5% in its policy review."
STORY_KEY = f"{STORY_TITLE}\n\n{STORY_TEXT}"  # what process_item embeds
PROFILE_LINE = "Economy & Banking"
RELATED = [1.0, 0.0, 0.0, 0.0]
UNRELATED = [0.0, 1.0, 0.0, 0.0]

READER_OUTPUT = {
    "summary": "RBI kept the repo rate unchanged at its policy review.",
    "section": "economy",
    "exam_tags": ["bank"],
    "facts": [{"statement": "The repo rate is 5.5%.", "subject": "repo rate", "value": "5.5%"}],
    "four_questions": {
        "what_happened": "RBI held the repo rate.",
        "why": "Inflation is within the target band.",
        "what_changes": "Loan rates stay where they are.",
        "how_it_affects_me": "EMIs do not change for now.",
    },
    "entities": ["RBI"],
}
SUPPORTED = {"supported": True, "quote": "kept the repo rate at 5.5%"}


@dataclass
class FactsHolder:
    old: int
    new_official: int
    new_from_news_only: int
    older_official: int
    repeat_of_old_value: int


class FailingCompleter(Completer):
    """Behaves like Ollama being down."""

    async def complete(self, *args: object, **kwargs: object) -> str:
        raise ConnectionError("ollama unreachable")


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


async def _make_deps(
    settings: Settings,
    tmp_path: Path,
    completer: Completer,
    profile_vector: list[float],
) -> PipelineDeps:
    vault, clean, jobs, raw = (tmp_path / d for d in ("vault", "clean", "parse-jobs", "raw"))
    for d in (vault / "context", clean, jobs, raw, settings.data_dir / "quarantine"):
        d.mkdir(parents=True, exist_ok=True)
    (vault / "context" / "interests.md").write_text(f"# Goals\n{PROFILE_LINE}\n", encoding="utf-8")
    engine = make_engine("app", settings)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    # Pipeline code stores every new raw item under source_id=1.
    async with factory() as s:
        s.add(
            Source(
                name="test-feed",
                url="https://pib.gov.in/rss.xml",
                host="pib.gov.in",
                section="economy",
                trust_tier="official",
            )
        )
        await s.commit()
    embedder = FakeEmbedder(dim=4, table={PROFILE_LINE: profile_vector, STORY_KEY: RELATED})
    return PipelineDeps(
        session_factory=factory,
        completer=completer,
        embedder=embedder,
        settings=settings,
        vault_root=vault,
        clean_dir=clean,
        jobs_dir=jobs,
        raw_dir=raw,
        allowed=ALLOWED,
        official=OFFICIAL,
    )


def _story_responses(items: int, checked: bool = True) -> FakeCompleter:
    per_item = [json.dumps(READER_OUTPUT)] + ([json.dumps(SUPPORTED)] if checked else [])
    return FakeCompleter(per_item * items)


@pytest.fixture
async def deps(pipeline_db: None, db_settings: Settings, tmp_path: Path) -> PipelineDeps:
    """Pipeline deps on the real database, with fake models (enough for two stories)."""
    return await _make_deps(db_settings, tmp_path, _story_responses(2), RELATED)


@pytest.fixture
async def deps_with_unrelated_profile(
    pipeline_db: None, db_settings: Settings, tmp_path: Path
) -> PipelineDeps:
    return await _make_deps(db_settings, tmp_path, _story_responses(1), UNRELATED)


@pytest.fixture
async def deps_with_failing_completer(
    pipeline_db: None, db_settings: Settings, tmp_path: Path
) -> PipelineDeps:
    return await _make_deps(db_settings, tmp_path, FailingCompleter(), RELATED)


def _write_result(clean_dir: Path, result: ParseResult) -> None:
    (clean_dir / f"{result.job_id}.result.json").write_text(
        result.model_dump_json(), encoding="utf-8"
    )


def _page(n: int, domain: str, verdict: str = "pass") -> ParseResult:
    outcome = "flag" if verdict == "flag" else "ok"
    return ParseResult(
        job_id=f"{n:032x}",
        kind="page",
        status="ok",
        doc=CleanDoc(
            url=f"https://www.{domain}/business/repo-rate-{n}",
            title=STORY_TITLE,
            text=STORY_TEXT,
            lang="en",
        ),
        intake=IntakeVerdict(
            verdict=verdict,
            steps=[IntakeStep(name="injection", outcome=outcome)],
            reasons=["injection_pattern"] if verdict == "flag" else [],
        ),
    )


@pytest.fixture
def page_result_from_news_domain(request: pytest.FixtureRequest) -> None:
    deps = _deps_of(request)
    _write_result(deps.clean_dir, _page(1, "thehindu.com"))


@pytest.fixture
def same_story_from_two_domains(deps: PipelineDeps) -> None:
    _write_result(deps.clean_dir, _page(1, "thehindu.com"))
    _write_result(deps.clean_dir, _page(2, "indianexpress.com"))


@pytest.fixture
def flagged_page_result_from_two_domains(deps: PipelineDeps) -> None:
    deps.completer = _story_responses(2, checked=False)  # flagged facts are never checked
    _write_result(deps.clean_dir, _page(1, "thehindu.com", verdict="flag"))
    _write_result(deps.clean_dir, _page(2, "indianexpress.com", verdict="flag"))


@pytest.fixture
def feed_result_with_one_bad_link(deps: PipelineDeps) -> None:
    _write_result(
        deps.clean_dir,
        ParseResult(
            job_id="f" * 32,
            kind="feed",
            status="ok",
            entries=[
                FeedEntry(title="Allowed", link="https://pib.gov.in/PressRelease.aspx?id=1"),
                FeedEntry(title="Not allowed", link="https://evil.example/phish"),
            ],
        ),
    )


def _deps_of(request: pytest.FixtureRequest) -> PipelineDeps:
    """Whichever deps fixture the test asked for."""
    for name in ("deps_with_unrelated_profile", "deps_with_failing_completer", "deps"):
        if name in request.fixturenames:
            return request.getfixturevalue(name)
    raise LookupError("page_result_from_news_domain needs a deps fixture")


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
