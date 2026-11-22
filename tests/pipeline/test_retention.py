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


# --- the quarantine folder (the parser writes it; the worker deletes there) ------------
# The worker mounts data/quarantine rw next to data/library rw, and the parser can write
# data/quarantine. A held job folder swapped for a link after a check must never lead a
# delete into the library.


def _with_held_rows(deps: PipelineDeps, rows: list) -> PipelineDeps:
    """Deps whose session returns `rows` for the expired quarantine query (the third)."""
    import dataclasses

    session = AsyncMock()
    session.add = MagicMock()

    def result(values):
        res = MagicMock()
        res.scalars.return_value.all.return_value = values
        return res

    session.execute.side_effect = [result([]), result([]), result(rows)]

    @asynccontextmanager
    async def factory():
        yield session

    return dataclasses.replace(deps, session_factory=factory)


def _held_row(path: Path):
    from techradar.db.models import QuarantineItem

    old = datetime.now(UTC) - timedelta(days=8)
    return QuarantineItem(
        job_id="c" * 32,
        path=str(path),
        origin="library",
        reasons=["macros"],
        created_at=old,
        expires_at=old + timedelta(days=7),
    )


async def test_expired_held_file_is_deleted(retention_deps: PipelineDeps):
    qdir = retention_deps.settings.data_dir / "quarantine"
    held = qdir / ("c" * 32) / ("a" * 64 + ".pdf")
    held.parent.mkdir()
    held.write_bytes(b"held")
    row = _held_row(held)
    r = await cleanup_retention(_with_held_rows(retention_deps, [row]), datetime.now(UTC))
    assert r["quarantine"] == 1 and not held.exists() and row.deleted_at is not None


async def test_expired_held_file_behind_a_swapped_folder_never_reaches_the_library(
    retention_deps: PipelineDeps, monkeypatch: pytest.MonkeyPatch
):
    # The race: the job folder is real when its path is checked, then the parser swaps it
    # for a link to library/originals before the unlink.
    import os

    book = _library_with_old_book(retention_deps)
    qdir = retention_deps.settings.data_dir / "quarantine"
    job = qdir / ("c" * 32)
    held = job / book.name
    job.mkdir()
    held.write_bytes(b"held copy")
    real_resolve = Path.resolve
    swapped: list[bool] = []

    def resolve_then_swap(self: Path, strict: bool = False) -> Path:
        out = real_resolve(self, strict=strict)
        if self == held and not swapped:
            swapped.append(True)
            os.rename(job, qdir / "moved-away")
            job.symlink_to(book.parent, target_is_directory=True)
        return out

    monkeypatch.setattr(Path, "resolve", resolve_then_swap)
    row = _held_row(held)
    await cleanup_retention(_with_held_rows(retention_deps, [row]), datetime.now(UTC))
    monkeypatch.undo()
    assert book.read_bytes() == b"%PDF-1.7 a book"


async def test_held_row_pointing_through_a_linked_folder_is_refused(
    retention_deps: PipelineDeps,
):
    book = _library_with_old_book(retention_deps)
    qdir = retention_deps.settings.data_dir / "quarantine"
    (qdir / ("c" * 32)).symlink_to(book.parent, target_is_directory=True)
    row = _held_row(qdir / ("c" * 32) / book.name)
    r = await cleanup_retention(_with_held_rows(retention_deps, [row]), datetime.now(UTC))
    assert book.read_bytes() == b"%PDF-1.7 a book" and r["quarantine"] == 0
    assert row.deleted_at is not None  # expired: never offered again


async def test_sweep_removes_old_held_files_and_their_empty_folders(
    retention_deps: PipelineDeps,
):
    qdir = retention_deps.settings.data_dir / "quarantine"
    old = qdir / ("d" * 32) / ("b" * 64 + ".pdf")
    fresh = qdir / ("e" * 32) / ("c" * 64 + ".pdf")
    for f in (old, fresh):
        f.parent.mkdir()
        f.write_bytes(b"x")
    _age(old, 30)
    r = await cleanup_retention(retention_deps, datetime.now(UTC))
    assert not old.exists() and not old.parent.exists()
    assert fresh.exists() and r["quarantine"] == 1


async def test_sweep_survives_a_dangling_link_and_never_follows_links(
    retention_deps: PipelineDeps,
):
    book = _library_with_old_book(retention_deps)
    qdir = retention_deps.settings.data_dir / "quarantine"
    (qdir / "dangling").symlink_to(qdir / "nowhere")
    (qdir / ("f" * 32)).symlink_to(book.parent, target_is_directory=True)
    old = qdir / ("a" * 32) / ("d" * 64 + ".pdf")
    old.parent.mkdir()
    old.write_bytes(b"x")
    _age(old, 30)
    await cleanup_retention(retention_deps, datetime.now(UTC))
    assert book.read_bytes() == b"%PDF-1.7 a book"
    assert not old.exists()


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
