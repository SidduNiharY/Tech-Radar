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


def _age(path: Path, days: int) -> None:
    import os

    t = (datetime.now(UTC) - timedelta(days=days)).timestamp()
    os.utime(path, (t, t), follow_symlinks=False)


def _library_with_old_book(deps: PipelineDeps) -> Path:
    """A 400-day-old book under the library originals folder (SEC-43)."""
    library = deps.settings.data_dir / "library"
    deps.settings = deps.settings.model_copy(update={"library_dir": library})
    originals = library / "originals"
    originals.mkdir(parents=True)
    book = originals / ("a" * 64 + ".pdf")
    book.write_bytes(b"%PDF-1.7 a book")
    _age(book, 400)
    return book


@pytest.mark.asyncio
async def test_retention_scans_never_reach_the_library(retention_deps: PipelineDeps):
    book = _library_with_old_book(retention_deps)
    # Links planted in every folder retention scans, all pointing at the book.
    for folder in (
        retention_deps.raw_dir,
        retention_deps.jobs_dir,
        retention_deps.settings.data_dir / "quarantine",
    ):
        link = folder / "planted.json"
        link.symlink_to(book)
        _age(link, 400)
    await cleanup_retention(retention_deps, datetime.now(UTC))
    assert book.read_bytes() == b"%PDF-1.7 a book"


@pytest.mark.db
async def test_retention_never_touches_library(deps: PipelineDeps):
    from techradar.db.models import Item, QuarantineItem, RawItem
    from tests.pipeline.conftest import _source_item

    book = _library_with_old_book(deps)
    old = datetime.now(UTC) - timedelta(days=400)
    async with deps.session_factory() as s:
        # Database rows that point into the library, as a corrupted or hostile row might.
        item = await _source_item(s, "rbi.org.in", 91)
        raw = await s.get(RawItem, item.raw_item_id)
        assert raw is not None
        raw.status, raw.fetched_at = "done", old
        raw.raw_name = f"../data/library/originals/{book.name}"
        item.status, item.processed_at, item.text_path = "written", old, str(book)
        s.add(
            QuarantineItem(
                job_id="b" * 32,
                path=str(book),
                origin="library",
                reasons=["macros"],
                created_at=old,
                expires_at=old + timedelta(days=7),
            )
        )
        await s.commit()
        assert isinstance(item, Item)

    r = await cleanup_retention(deps, datetime.now(UTC))
    assert book.exists() and book.read_bytes() == b"%PDF-1.7 a book"
    assert r["raw"] == 0 and r["clean"] == 0 and r["quarantine"] == 0


def test_safe_unlink_is_not_fooled_by_a_sibling_folder_with_the_same_prefix(tmp_path: Path):
    from techradar.pipeline.retention import _safe_unlink

    root = tmp_path / "quarantine"
    root.mkdir()
    sibling = tmp_path / "quarantine-evil"
    sibling.mkdir()
    victim = sibling / "book.pdf"
    victim.write_bytes(b"keep")
    assert _safe_unlink(victim, {root.resolve()}) is False
    assert victim.exists()
    inside = root / "x.pdf"
    inside.write_bytes(b"held")
    assert _safe_unlink(inside, {root.resolve()}) is True
    assert not inside.exists()
