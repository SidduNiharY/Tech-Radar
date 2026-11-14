"""Tests for vault and library RAG indexer (Phase 2b Task 3 / SEC-06, SEC-17, SEC-39, SEC-40)."""

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from techradar.db.engine import make_engine
from techradar.db.models import Chunk
from techradar.rag.indexer import (
    LIBRARY_SCAN_EXCLUDE,
    IndexDeps,
    collect_clipping_results,
    doc_meta,
    plan_clipping_jobs,
    scan_vault,
    sync_index,
)
from techradar.settings import Settings
from tests.fakes import FakeEmbedder


def test_scan_vault_skips_obsidian_symlinks_and_big_files(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()

    # Normal note
    (vault / "note.md").write_text("# Note\nContent")

    # .obsidian file
    obs = vault / ".obsidian"
    obs.mkdir()
    (obs / "app.json").write_text("{}")
    (obs / "hidden.md").write_text("# Hidden")

    # .trash file
    trash = vault / ".trash"
    trash.mkdir()
    (trash / "deleted.md").write_text("# Deleted")

    # Big file (> 2MB)
    big = vault / "large.md"
    big.write_bytes(b"x" * (2_000_001))

    # Symlink
    target = tmp_path / "target.md"
    target.write_text("# Target")
    sym = vault / "sym.md"
    try:
        sym.symlink_to(target)
    except OSError:
        pass

    results = scan_vault(vault)
    assert "note.md" in results
    assert ".obsidian/hidden.md" not in results
    assert ".trash/deleted.md" not in results
    assert "large.md" not in results
    assert "sym.md" not in results


def test_doc_meta_reads_generated_and_verified():
    m = doc_meta({"kind": "news", "verified_headline": True, "generated": True})
    assert (m.doc_kind, m.verified, m.generated) == ("news", True, True)


def test_doc_meta_defaults_to_user_note():
    assert doc_meta({}).doc_kind == "user"


def test_scan_vault_never_opens_skipped_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    (tmp_path / "passwords.md").write_text("secret")
    (tmp_path / "public.md").write_text("public note")

    opened: list[str] = []
    orig_open = Path.open

    def spy_open(self: Path, *args: Any, **kwargs: Any):
        opened.append(self.name)
        return orig_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", spy_open)
    res = scan_vault(tmp_path, skip=["passwords.md"])

    assert "passwords.md" not in res
    assert "public.md" in res
    assert "passwords.md" not in opened


@pytest.fixture
def index_deps(tmp_path: Path, rag_db: None) -> IndexDeps:
    vault = tmp_path / "vault"
    library = tmp_path / "library"
    library_inbox = tmp_path / "library-inbox"
    raw = tmp_path / "raw"
    jobs = tmp_path / "jobs"
    clean = tmp_path / "clean"
    for d in (vault, library, library_inbox, raw, jobs, clean):
        d.mkdir(parents=True, exist_ok=True)

    db_settings = Settings(
        telegram_owner_chat_id=1,
        db_host="127.0.0.1",
        db_port=55432,
        db_name="techradar",
        secrets_dir=Path("secrets"),
    )
    engine = make_engine("app", db_settings)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    embedder = FakeEmbedder(dim=1024)

    return IndexDeps(
        session_factory=session_factory,
        embedder=embedder,
        vault_root=vault,
        library_dir=library,
        library_inbox=library_inbox,
        raw_dir=raw,
        jobs_dir=jobs,
        clean_dir=clean,
        skip=(),
    )


# DB integration tests
@pytest.mark.db
async def test_sync_adds_then_updates_then_removes(index_deps: IndexDeps):
    vault = index_deps.vault_root
    note = vault / "test_note.md"

    # 1. Add
    note.write_text("# First Title\nInitial body content.")
    c1 = await sync_index(index_deps)
    assert c1["added"] == 1 and c1["updated"] == 0 and c1["removed"] == 0

    # 2. Update
    note.write_text("# Updated Title\nUpdated body content.")
    c2 = await sync_index(index_deps)
    assert c2["added"] == 0 and c2["updated"] == 1 and c2["removed"] == 0

    # 3. Remove
    note.unlink()
    c3 = await sync_index(index_deps)
    assert c3["added"] == 0 and c3["updated"] == 0 and c3["removed"] == 1


@pytest.mark.db
async def test_sync_updates_changed_note(index_deps: IndexDeps):
    vault = index_deps.vault_root
    note = vault / "changed_note.md"
    note.write_text("# Old Heading\nOld text content.")
    await sync_index(index_deps)

    note.write_text("# New Heading\nNew distinct content.")
    await sync_index(index_deps)

    async with index_deps.session_factory() as session:
        result = await session.execute(
            select(Chunk.text).where(Chunk.doc_path == "changed_note.md")
        )
        texts = [r[0] for r in result.all()]
        assert any("New distinct content" in t for t in texts)
        assert not any("Old text content" in t for t in texts)


@pytest.mark.db
async def test_clipping_goes_through_gateway_and_is_flagged(index_deps: IndexDeps):
    clippings_dir = index_deps.vault_root / "Clippings"
    clippings_dir.mkdir(parents=True, exist_ok=True)
    clipping_file = clippings_dir / "a.md"
    clipping_file.write_text("# Clipped Article\nClipped malicious prompt.")

    jobs = plan_clipping_jobs(
        index_deps.vault_root,
        {"Clippings/a.md": "dummyhash"},
        index_deps.raw_dir,
    )
    assert len(jobs) == 1
    assert jobs[0].origin == "clipping"

    # Simulate parse result from gateway with flag verdict
    clean_dir = index_deps.clean_dir
    clean_dir.mkdir(parents=True, exist_ok=True)
    res_path = clean_dir / f"{jobs[0].job_id}.result.json"
    res_path.write_text(
        f'{{"job_id": "{jobs[0].job_id}", "kind": "md", "status": "ok", '
        f'"purpose": "clipping", "doc": {{"url": "clipping:Clippings/a.md", '
        f'"title": "Clipped", "text": "Clipped content", "lang": "en", "truncated": false}}, '
        f'"intake": {{"verdict": "flag", "steps": [], "reasons": ["suspicious"]}}}}'
    )

    await collect_clipping_results(index_deps)

    async with index_deps.session_factory() as session:
        result = await session.execute(
            select(Chunk.flagged).where(Chunk.doc_path == "Clippings/a.md")
        )
        flags = [r[0] for r in result.all()]
        assert flags == [True]


def test_library_scan_skips_work_in_progress_folders(tmp_path: Path):
    lib = tmp_path / "library"
    for rel in (
        "text/7/parts/1.md",  # part text of an unfinished doc
        "text/7/01.md",  # chapter file: indexed by chapter, not by this scan
        "media/7/notes.md",
        "slug.md",
        "other/keep.md",
        "text.md",  # a file that is merely called text
    ):
        f = lib / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("# Heading\nbody")
    got = scan_vault(lib, exclude_dirs=LIBRARY_SCAN_EXCLUDE)
    assert sorted(got) == ["other/keep.md", "slug.md", "text.md"]
    # without the exclusion the old behaviour is unchanged
    assert "text/7/parts/1.md" in scan_vault(lib)


async def test_sync_index_never_embeds_library_text_or_media(tmp_path: Path):
    vault, lib = tmp_path / "vault", tmp_path / "library"
    vault.mkdir()
    for rel in ("text/7/parts/1.md", "text/7/01.md", "media/7/x.md", "legacy.md"):
        f = lib / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("# Heading\nbody of " + rel)
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    session = MagicMock()
    session.execute = AsyncMock(return_value=result)
    session.commit = AsyncMock()
    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=session)
    factory.return_value.__aexit__ = AsyncMock(return_value=False)
    embedder = FakeEmbedder()
    deps = IndexDeps(
        session_factory=factory,
        embedder=embedder,
        vault_root=vault,
        library_dir=lib,
        library_inbox=tmp_path / "inbox",
        raw_dir=tmp_path / "raw",
        jobs_dir=tmp_path / "jobs",
        clean_dir=tmp_path / "clean",
    )
    counts = await sync_index(deps)
    paths = {c.args[0].doc_path for c in session.add.call_args_list}
    assert paths == {"library/legacy.md"} and counts["added"] == 1
    assert all(
        "body of text/" not in t and "body of media/" not in t for b in embedder.calls for t in b
    )


def test_the_dead_library_collector_is_gone():
    import techradar.rag.indexer as indexer

    assert not hasattr(indexer, "collect_library_results")
