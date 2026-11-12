"""Tests for pipeline worker orchestration and processing."""

import json
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import func, select

from techradar.db.models import Fact, IntakeLog, Item, RawItem
from techradar.pipeline.process import (
    PipelineDeps,
    collect_results,
    process_new_items,
)
from techradar.schemas.pipeline import (
    CleanDoc,
    IntakeStep,
    IntakeVerdict,
    ParseResult,
)
from techradar.settings import Settings
from tests.fakes import FakeCompleter, FakeEmbedder

GOOD_READER = {
    "summary": "RBI maintained current interest rate levels.",
    "section": "economy",
    "exam_tags": ["bank"],
    "facts": [
        {
            "statement": "Repo rate stays at 5.5%.",
            "subject": "repo rate",
            "value": "5.5%",
        }
    ],
    "four_questions": {
        "what_happened": "Rates held constant.",
        "why": "Inflation remains balanced.",
        "what_changes": "No immediate EMI shifts.",
        "how_it_affects_me": "Steady loan rates.",
    },
    "entities": ["RBI"],
}


async def count_rows(deps: PipelineDeps, model: type) -> int:
    async with deps.session_factory() as s:
        return int((await s.execute(select(func.count()).select_from(model))).scalar_one())


async def item_flags(deps: PipelineDeps) -> list[str]:
    async with deps.session_factory() as s:
        return sorted((await s.execute(select(Item.flags))).scalar_one())


async def fact_statuses(deps: PipelineDeps) -> set[str]:
    async with deps.session_factory() as s:
        return set((await s.execute(select(Fact.status))).scalars().all())


@pytest.fixture
def test_settings(tmp_path: Path) -> Settings:
    return Settings(
        telegram_owner_chat_id=1,
        secrets_dir=tmp_path / "secrets",
        data_dir=tmp_path / "data",
    )


@pytest.fixture
def fake_deps(tmp_path: Path, test_settings: Settings) -> PipelineDeps:
    vault = tmp_path / "vault"
    clean = tmp_path / "clean"
    jobs = tmp_path / "parse-jobs"
    raw = tmp_path / "raw"
    for d in (vault, clean, jobs, raw):
        d.mkdir(parents=True, exist_ok=True)

    # Seed interests
    context_dir = vault / "context"
    context_dir.mkdir(parents=True, exist_ok=True)
    (context_dir / "interests.md").write_text("# Goals\nEconomy & Banking\n")

    completer = FakeCompleter(
        [
            json.dumps(GOOD_READER),
            json.dumps({"supported": True, "quote": "Repo rate stays at 5.5%."}),
        ]
    )
    embedder = FakeEmbedder(dim=4, table={"Economy & Banking": [1.0, 0.0, 0.0, 0.0]})

    session = AsyncMock()
    session.add = MagicMock()
    exec_mock = MagicMock()
    exec_mock.scalar_one_or_none.return_value = None
    exec_mock.scalars.return_value.all.return_value = []
    session.execute.return_value = exec_mock

    @asynccontextmanager
    async def factory():
        yield session

    return PipelineDeps(
        session_factory=factory,
        completer=completer,
        embedder=embedder,
        settings=test_settings,
        vault_root=vault,
        clean_dir=clean,
        jobs_dir=jobs,
        raw_dir=raw,
        allowed=frozenset({"rbi.org.in", "pib.gov.in"}),
        official=frozenset({"rbi.org.in"}),
    )


@pytest.mark.asyncio
async def test_collect_results_feed_links(fake_deps: PipelineDeps):
    # Create feed result with one good link and one invalid link
    feed_res = ParseResult(
        job_id="a" * 32,
        kind="feed",
        status="ok",
        entries=[
            {
                "title": "Good Entry",
                "link": "https://rbi.org.in/press/1",
                "published": None,
                "summary": "Summary 1",
            },
            {
                "title": "Bad Entry",
                "link": "https://evil.example/malicious",
                "published": None,
                "summary": "Summary 2",
            },
        ],
    )
    result_path = fake_deps.clean_dir / f"{feed_res.job_id}.result.json"
    result_path.write_text(feed_res.model_dump_json(), encoding="utf-8")

    counts = await collect_results(fake_deps)
    assert counts["feeds"] == 1
    assert counts["skipped_links"] == 1
    assert not result_path.exists()


@pytest.mark.asyncio
async def test_collect_results_page_intake_flag(fake_deps: PipelineDeps):
    doc = CleanDoc(
        url="https://rbi.org.in/press/1",
        title="RBI Repo Rate Policy",
        text="The repo rate stays at 5.5% as of today.",
        lang="en",
        truncated=False,
    )
    page_res = ParseResult(
        job_id="b" * 32,
        kind="page",
        status="ok",
        doc=doc,
        intake=IntakeVerdict(
            verdict="flag",
            steps=[IntakeStep(name="injection", outcome="flag", detail="quoted injection")],
            reasons=["injection pattern"],
        ),
    )
    result_path = fake_deps.clean_dir / f"{page_res.job_id}.result.json"
    result_path.write_text(page_res.model_dump_json(), encoding="utf-8")

    counts = await collect_results(fake_deps)
    assert counts["docs"] == 1
    assert result_path.exists()  # Kept on disk for text access by worker


@pytest.mark.db
async def test_collect_feed_result_inserts_only_allowlisted_links(
    deps, feed_result_with_one_bad_link
):
    counts = await collect_results(deps)
    assert counts["skipped_links"] == 1 and await count_rows(deps, RawItem) == 1


@pytest.mark.db
async def test_end_to_end_fake_pipeline(deps, page_result_from_news_domain):
    await collect_results(deps)
    assert await process_new_items(deps) == {"written": 1}
    md = next((deps.vault_root / "wiki/news").rglob("*.md")).read_text()
    assert "generated: true" in md and "⚠️ unverified" in md


@pytest.mark.db
async def test_two_sources_one_story_one_note(deps, same_story_from_two_domains):
    await collect_results(deps)
    await process_new_items(deps)
    notes = list((deps.vault_root / "wiki/news").rglob("*.md"))
    assert len(notes) == 1 and "✅ verified" in notes[0].read_text()


@pytest.mark.db
async def test_filtered_out_below_relevance(
    deps_with_unrelated_profile, page_result_from_news_domain
):
    await collect_results(deps_with_unrelated_profile)
    assert await process_new_items(deps_with_unrelated_profile) == {"filtered_out": 1}


@pytest.mark.db
async def test_ollama_error_marks_needs_review(
    deps_with_failing_completer, page_result_from_news_domain
):
    await collect_results(deps_with_failing_completer)
    for _ in range(3):
        await process_new_items(deps_with_failing_completer)
    assert await item_flags(deps_with_failing_completer) == ["model_unavailable"]


@pytest.mark.db
async def test_flagged_item_facts_never_verified(deps, flagged_page_result_from_two_domains):
    await collect_results(deps)
    await process_new_items(deps)
    assert await fact_statuses(deps) == {"unverified"}
    assert await count_rows(deps, IntakeLog) == 2
