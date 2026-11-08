"""Tests for retention cleanup policy."""

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from techradar.pipeline.process import PipelineDeps
from techradar.pipeline.retention import cleanup_retention
from techradar.settings import Settings
from tests.fakes import FakeCompleter, FakeEmbedder


@pytest.fixture
def retention_deps(tmp_path: Path) -> PipelineDeps:
    vault = tmp_path / "vault"
    clean = tmp_path / "clean"
    jobs = tmp_path / "parse-jobs"
    raw = tmp_path / "raw"
    data = tmp_path / "data"
    for d in (vault, clean, jobs, raw, data / "quarantine"):
        d.mkdir(parents=True, exist_ok=True)

    session = AsyncMock()
    session.add = MagicMock()
    # Mock empty db results for unit test
    empty_res = MagicMock()
    empty_res.scalars.return_value.all.return_value = []
    session.execute.return_value = empty_res

    @asynccontextmanager
    async def factory():
        yield session

    settings = Settings(
        telegram_owner_chat_id=1,
        secrets_dir=tmp_path / "secrets",
        data_dir=data,
    )

    return PipelineDeps(
        session_factory=factory,
        completer=FakeCompleter([]),
        embedder=FakeEmbedder(),
        settings=settings,
        vault_root=vault,
        clean_dir=clean,
        jobs_dir=jobs,
        raw_dir=raw,
        allowed=frozenset({"rbi.org.in"}),
        official=frozenset({"rbi.org.in"}),
    )


@pytest.mark.asyncio
async def test_cleanup_retention_removes_orphan_job_files(retention_deps: PipelineDeps):
    orphan_file = retention_deps.jobs_dir / "old.job.json"
    orphan_file.write_text("{}", encoding="utf-8")

    # Set mtime to 2 days ago
    old_time = (datetime.now(UTC) - timedelta(days=2)).timestamp()
    import os

    os.utime(orphan_file, (old_time, old_time))

    counts = await cleanup_retention(retention_deps, datetime.now(UTC))
    assert counts["orphans"] >= 1
    assert not orphan_file.exists()


@pytest.mark.asyncio
async def test_cleanup_retention_preserves_fresh_files(retention_deps: PipelineDeps):
    fresh_file = retention_deps.jobs_dir / "fresh.job.json"
    fresh_file.write_text("{}", encoding="utf-8")

    counts = await cleanup_retention(retention_deps, datetime.now(UTC))
    assert counts["orphans"] == 0
    assert fresh_file.exists()


@pytest.mark.db
async def test_retention_deletes_old_files(deps, finished_rows_8_days_old):
    r = await cleanup_retention(deps, datetime.now(UTC))
    assert r["raw"] >= 1 and r["clean"] >= 1 and not any(deps.raw_dir.iterdir())


@pytest.mark.db
async def test_quarantine_deleted_after_seven_days(deps, quarantined_item_8_days_old):
    r = await cleanup_retention(deps, datetime.now(UTC))
    assert r["quarantine"] == 1
