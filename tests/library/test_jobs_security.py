"""Security integration of the bulk library collector (Phase 2c, SEC-14/15/43/44/57).

The gateway's verdict travels with every library result; the collector records it on the doc
(fail closed) and holds quarantined docs for the owner.
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from techradar.db.engine import make_engine
from techradar.db.models import LibraryDoc, LibraryPart
from techradar.library import jobs as jobs_mod
from techradar.library.jobs import collect_bulk_results
from techradar.schemas.pipeline import CleanDoc, IntakeStep, IntakeVerdict, ParseResult
from techradar.settings import Settings
from tests.library.test_jobs import Dirs, _collect, _doc, _fake_doc, _FakeSession

FULL_ID = "c" * 32


class _Recording(_FakeSession):
    """A fake session that remembers every statement it executed."""

    def __init__(self, objs: dict, rows: list | None = None) -> None:
        super().__init__(objs, rows)
        self.statements: list = []

    async def execute(self, stmt, *a, **k):
        self.statements.append(stmt)
        return await super().execute(stmt, *a, **k)

    def chunk_updates(self) -> list[str]:
        out = []
        for s in self.statements:
            text = str(s)
            if text.startswith("UPDATE techradar.chunks"):
                out.append(text)
        return out


def _intake(verdict: str | None) -> IntakeVerdict | None:
    if verdict is None:
        return None
    outcome = {"pass": "ok", "flag": "flag", "quarantine": "quarantine", "reject": "reject"}
    step = IntakeStep(name="injection", outcome=outcome[verdict], detail="d")  # type: ignore[arg-type]
    return IntakeVerdict(verdict=verdict, steps=[step], reasons=["d"])  # type: ignore[arg-type]


def _full_result(
    clean: Path, verdict: str | None, *, status: str = "ok", job_id: str = FULL_ID
) -> None:
    clean.mkdir(parents=True, exist_ok=True)
    doc = CleanDoc(url="library:1", title="t", text="# One\nalpha", lang="en")
    res = ParseResult(
        job_id=job_id, kind="docx", status=status, purpose="library",  # type: ignore[arg-type]
        doc=doc if status == "ok" else None, intake=_intake(verdict),
    )  # fmt: skip
    (clean / f"{job_id}.result.json").write_text(res.model_dump_json(), encoding="utf-8")


async def _collect_full(tmp_path: Path, verdict: str | None, *, flagged: bool = False, **kw):
    lib, clean, jobs = tmp_path / "lib", tmp_path / "clean", tmp_path / "jobs"
    doc = _fake_doc("docx")
    doc.flagged = flagged
    jobs_mod._write_record(lib, FULL_ID, jobs_mod.JobRecord(doc_id=1, kind="full"))
    _full_result(clean, verdict, **kw)
    session = _Recording({(LibraryDoc, 1): doc}, rows=[])
    counts = await collect_bulk_results(
        session,  # type: ignore[arg-type]
        clean_dir=clean, jobs_dir=jobs, library_dir=lib, part_pages=5,
    )  # fmt: skip
    return doc, session, counts


# --- A. the gateway verdict is recorded, failing closed ------------------------------


async def test_result_without_intake_flags_the_doc(tmp_path: Path):
    doc, session, counts = await _collect_full(tmp_path, None)
    assert counts["handled"] == 1
    assert doc.flagged is True


async def test_flag_verdict_flags_the_doc(tmp_path: Path):
    doc, _session, _ = await _collect_full(tmp_path, "flag")
    assert doc.flagged is True


async def test_pass_verdict_leaves_the_doc_unflagged(tmp_path: Path):
    doc, session, _ = await _collect_full(tmp_path, "pass")
    assert doc.flagged is False
    assert session.chunk_updates() == []


async def test_inconsistent_verdict_on_an_ok_result_flags_the_doc(tmp_path: Path):
    """status ok with a quarantine/reject verdict breaks the contract: fail closed."""
    for verdict in ("quarantine", "reject"):
        doc, _s, _ = await _collect_full(tmp_path / verdict, verdict)
        assert doc.flagged is True


async def test_pass_never_clears_an_existing_flag(tmp_path: Path):
    doc, session, _ = await _collect_full(tmp_path, "pass", flagged=True)
    assert doc.flagged is True
    assert session.chunk_updates() == []  # nothing changed, nothing to carry


async def test_newly_flagged_doc_flags_its_chunks_in_the_same_transaction(tmp_path: Path):
    doc, session, _ = await _collect_full(tmp_path, "flag")
    [stmt] = session.chunk_updates()
    assert "flagged" in stmt and "doc_id" in stmt and "doc_kind" in stmt
    assert session.committed == 1  # one commit: the doc and its chunks together


async def test_a_parser_error_without_intake_does_not_flag(tmp_path: Path):
    """An error result carries no content, so nothing of it can reach the library."""
    doc, _session, _ = await _collect_full(tmp_path, None, status="error")
    assert doc.flagged is False


async def test_media_segment_without_intake_flags_the_doc(tmp_path: Path):
    lib, clean, jobs = tmp_path / "lib", tmp_path / "clean", tmp_path / "jobs"
    doc = _fake_doc("video")
    doc.flagged = False
    doc.keep_media = True
    jid = "e" * 32
    part = SimpleNamespace(
        id=4, ordinal=0, status="pending", job_id=jid, attempts=0, page_start=None,
        page_end=None, ts_start=0.0, ts_end=600.0, result_path=None,
    )  # fmt: skip
    audio = lib / "media" / "1" / "audio" / "seg-00000.flac"
    audio.parent.mkdir(parents=True)
    audio.write_bytes(b"fLaC")
    jobs_mod._write_record(lib, jid, jobs_mod.JobRecord(doc_id=1, kind="media", part_id=4))
    clean.mkdir()
    seg = {"audio_file": "audio/seg-00000.flac", "slides": []}
    res = ParseResult(
        job_id=jid, kind="video", status="ok", purpose="library",
        doc=CleanDoc(url="library:1", title="t", text=json.dumps(seg), lang="en"),
    )  # fmt: skip
    (clean / f"{jid}.result.json").write_text(res.model_dump_json(), encoding="utf-8")
    session = _Recording({(LibraryDoc, 1): doc, (LibraryPart, 4): part}, rows=["done"])
    await collect_bulk_results(
        session,  # type: ignore[arg-type]
        clean_dir=clean, jobs_dir=jobs, library_dir=lib, part_pages=5,
    )  # fmt: skip
    assert part.status == "done" and doc.flagged is True


# --- database tests ------------------------------------------------------------------


@pytest.fixture
async def db() -> AsyncGenerator[AsyncSession]:
    """A session whose changes are rolled back after the test."""
    settings = Settings(
        telegram_owner_chat_id=1, db_host="127.0.0.1", db_port=55432, db_name="techradar",
        secrets_dir=Path("secrets"),
    )  # fmt: skip
    engine = make_engine("app", settings)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s
        await s.rollback()
    await engine.dispose()


@pytest.fixture
def dirs(tmp_path: Path) -> Dirs:
    return Dirs(tmp_path)


@pytest.mark.db
async def test_db_flag_after_chunks_exist_flags_the_chunks(db: AsyncSession, dirs: Dirs):
    from sqlalchemy import select

    from techradar.db.models import Chunk
    from techradar.library.jobs import plan_doc

    doc = await _doc(db, kind="docx")
    other = await _doc(db, kind="docx")
    [job_id] = await plan_doc(db, doc.id, jobs_dir=dirs.jobs, library_dir=dirs.lib, commit=False)
    for d in (doc, other):
        db.add(
            Chunk(
                doc_path=f"library/{d.id}", doc_kind="library", title="t", ordinal=1, text="x",
                lang="en", content_hash="0" * 64, doc_id=d.id, flagged=False,
            )
        )  # fmt: skip
    await db.flush()
    _full_result(dirs.clean, "flag", job_id=job_id)
    await _collect(db, dirs)
    await db.refresh(doc)
    assert doc.flagged is True
    rows = (
        await db.execute(
            select(Chunk.doc_id, Chunk.flagged).where(Chunk.doc_id.in_([doc.id, other.id]))
        )
    ).all()
    assert dict(rows) == {doc.id: True, other.id: False}
