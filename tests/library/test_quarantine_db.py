"""db tests for the two-step release and the delete of held files (Phase 2c Task 10).

A library doc is never gated in the bot or worker: release marks it, and its jobs are re-run
by the parser with `owner_released=True`. The gate here is the real Intake Gateway with real
fixtures (only parsing is faked); for library docs it runs on the re-planned job, as the
parser would, and for other held files it is the injected release gate.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import AsyncGenerator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from techradar.db.engine import make_engine
from techradar.db.models import (
    BookEval,
    Chunk,
    LibraryChapter,
    LibraryDoc,
    LibraryPart,
    QuarantineItem,
    StarterPack,
    StarterPackItem,
)
from techradar.intake.av import AvResult
from techradar.intake.gateway import gate_job
from techradar.library.quarantine import (
    delete_item,
    doc_flagged,
    doc_released,
    hold_library_doc,
    list_quarantine,
    purge_deleted_held_docs,
    release,
    release_prompt,
)
from techradar.schemas.pipeline import CleanDoc, ParseJob, ParseResult
from techradar.settings import Settings
from techradar.tickets import create_ticket, run_confirmed
from tests.intake.library_fixtures import make_docx

pytestmark = pytest.mark.db

FIX_DIR = Path(__file__).parents[1] / "intake" / "fixtures"
LIMITS = yaml.safe_load(Path("infra/intake/limits.yaml").read_text())
TODAY = date(2026, 11, 14)
NOW = datetime(2026, 11, 14, 9, 0, tzinfo=UTC)
OWNER = 1234


def _exists(p: Path) -> bool:
    return p.exists()


class CleanAv:
    def scan(self, path: Path) -> AvResult:
        return AvResult(status="clean", db_date=TODAY)


@pytest.fixture
def db_settings() -> Settings:
    return Settings(
        telegram_owner_chat_id=OWNER,
        db_host="127.0.0.1",
        db_port=55432,
        db_name="techradar",
        secrets_dir=Path("secrets"),
    )


@pytest.fixture
async def session(db_settings: Settings) -> AsyncGenerator[AsyncSession]:
    """A session whose changes are rolled back after the test."""
    engine = make_engine("app", db_settings)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s
        await s.rollback()
    await engine.dispose()


class Gate:
    """The real gateway, run on the held copy with owner_released=True."""

    def __init__(self, qdir: Path) -> None:
        self.qdir = qdir
        self.calls = 0

    async def __call__(self, item: QuarantineItem) -> ParseResult:
        self.calls += 1
        held = Path(item.path)
        kind = held.suffix.lstrip(".")
        job = ParseJob(
            job_id=item.job_id,
            kind=kind,  # type: ignore[arg-type]
            raw_name=held.name,
            url="library:1",
            source_id=0,
            origin="library",
            purpose="library",
        )

        def parse(j: ParseJob) -> ParseResult:
            doc = CleanDoc(url="library:1", title="t", text="Hello library", lang="en")
            return ParseResult(job_id=j.job_id, kind=j.kind, status="ok", doc=doc)

        return gate_job(
            job,
            held.parent,
            self.qdir,
            av=CleanAv(),
            allowed_hosts=frozenset(),
            limits=LIMITS,
            parse=parse,
            parse_pixels=parse,
            today=TODAY,
            owner_released=True,
        )


async def _held_doc(
    session: AsyncSession, qdir: Path, *, kind: str = "docx", fixture: str | None = None
) -> tuple[LibraryDoc, QuarantineItem]:
    sha = os.urandom(32).hex()
    name = f"{sha}.{kind}"
    doc = LibraryDoc(
        sha256=sha,
        title="Macro Book",
        kind=kind,
        origin="library",
        original_path=f"originals/{name}",
        size_bytes=1000,
        status="quarantined",
        trust="my_own",
    )
    session.add(doc)
    await session.flush()
    job_id = os.urandom(16).hex()
    held = qdir / job_id / name
    held.parent.mkdir(parents=True)
    if fixture is None:
        make_docx(held, extra={"word/vbaProject.bin": b"\xd0\xcf\x11\xe0fake"})
    else:
        shutil.copyfile(FIX_DIR / fixture, held)
    os.chmod(held, 0o400)
    item = await hold_library_doc(
        session, doc, job_id=job_id, quarantine_dir=qdir, reasons=["macros"], chat_id=OWNER
    )
    assert item.path == str(held)
    return doc, item


async def _release_ticket(session: AsyncSession, item_id: int, *, at: datetime = NOW) -> str:
    """Step 1 as `qrel:<id>` does it: the prompt, stored as a ticket for chat OWNER."""
    text = await release_prompt(session, item_id)
    assert text is not None
    t = await create_ticket(
        session, session_id=f"tg:{OWNER}", channel="telegram", action="quarantine.release",
        args={"id": item_id}, summary=text, now=at,
    )  # fmt: skip
    return t.token


async def test_release_processes_as_flagged(session: AsyncSession, tmp_path: Path) -> None:
    doc, item = await _held_doc(session, tmp_path / "q")
    assert await doc_flagged(session, doc.id) is False

    assert await release_prompt(session, item.id) == (
        "Release Macro Book? It will be processed as flagged: searchable, "
        "but never used for facts, cards or questions."
    )
    token = await _release_ticket(session, item.id)
    result = await run_confirmed(session, token, f"tg:{OWNER}", NOW + timedelta(seconds=30))
    assert result == ("ok", "Released. It will be processed as flagged.")
    assert await doc_flagged(session, doc.id) is True
    await session.refresh(item)
    await session.refresh(doc)
    assert item.released_at is not None and item.deleted_at is None
    assert doc.status == "queued"  # planned again; its jobs run as owner-released


async def test_release_ticket_expires(session: AsyncSession, tmp_path: Path) -> None:
    doc, item = await _held_doc(session, tmp_path / "q")
    token = await _release_ticket(session, item.id)
    result = await run_confirmed(session, token, f"tg:{OWNER}", NOW + timedelta(seconds=61))
    assert result == ("expired", None)
    assert await doc_flagged(session, doc.id) is False
    await session.refresh(item)
    assert item.released_at is None


async def test_double_confirm_is_a_no_op(session: AsyncSession, tmp_path: Path) -> None:
    _doc, item = await _held_doc(session, tmp_path / "q")
    gate = Gate(tmp_path / "q")
    token = await _release_ticket(session, item.id)
    first = await run_confirmed(session, token, f"tg:{OWNER}", NOW)
    second = await run_confirmed(session, token, f"tg:{OWNER}", NOW)
    assert (first[0], second) == ("ok", ("used", None))
    # A new prompt for a released item is refused, so it cannot be released twice.
    assert await release_prompt(session, item.id) is None
    assert await release(session, item.id, gate=gate, now=NOW) == "not_found"
    assert gate.calls == 0


async def test_another_chat_cannot_confirm(session: AsyncSession, tmp_path: Path) -> None:
    doc, item = await _held_doc(session, tmp_path / "q")
    token = await _release_ticket(session, item.id)
    assert await run_confirmed(session, token, "tg:-100", NOW) == ("wrong_session", None)
    assert await doc_flagged(session, doc.id) is False


async def test_prompt_for_unknown_or_deleted_item_is_refused(
    session: AsyncSession, tmp_path: Path
) -> None:
    assert await release_prompt(session, -1) is None
    _doc, item = await _held_doc(session, tmp_path / "q")
    assert await delete_item(session, item.id, quarantine_dir=tmp_path / "q", now=NOW) == "deleted"
    assert await release_prompt(session, item.id) is None
    assert await release(session, item.id, gate=Gate(tmp_path / "q"), now=NOW) == "not_found"


async def test_released_reject_stays_reject(session: AsyncSession, tmp_path: Path) -> None:
    """Release, then the parser re-runs the doc's job as owner-released: a reject stays one."""
    from techradar.library.jobs import collect_bulk_results, plan_doc

    qdir, lib = tmp_path / "q", tmp_path / "library"
    doc, item = await _held_doc(session, qdir, kind="pdf", fixture="polyglot.pdf")
    original = lib / doc.original_path
    original.parent.mkdir(parents=True)
    shutil.copyfile(FIX_DIR / "polyglot.pdf", original)
    assert await release(session, item.id, gate=None, now=NOW) == "released"
    await session.refresh(doc)
    assert doc.status == "queued"

    jobs, clean = tmp_path / "jobs", tmp_path / "clean"
    [job_id] = await plan_doc(session, doc.id, jobs_dir=jobs, library_dir=lib, commit=False)
    job = ParseJob.model_validate_json((jobs / f"{job_id}.job.json").read_text())
    assert job.owner_released is True

    def parse(j: ParseJob) -> ParseResult:
        return ParseResult(job_id=j.job_id, kind=j.kind, status="ok")

    result = gate_job(
        job, lib / "originals", qdir, av=CleanAv(), allowed_hosts=frozenset(), limits=LIMITS,
        parse=parse, parse_pixels=parse, today=TODAY, owner_released=job.owner_released,
    )  # fmt: skip
    assert result.status == "rejected"
    clean.mkdir()
    result = result.model_copy(update={"purpose": "library"})
    (clean / f"{job_id}.result.json").write_text(result.model_dump_json(), encoding="utf-8")
    await collect_bulk_results(
        session, clean_dir=clean, jobs_dir=jobs, library_dir=lib, part_pages=25, commit=False,
        quarantine_dir=qdir,
    )  # fmt: skip
    await session.refresh(doc)
    assert doc.status == "rejected"


async def test_a_doc_held_again_after_its_release_is_never_released_twice(
    session: AsyncSession, tmp_path: Path
) -> None:
    qdir = tmp_path / "q"
    doc, item = await _held_doc(session, qdir)
    assert await release(session, item.id, gate=None, now=NOW) == "released"
    # its owner-released job came back quarantined anyway (should not happen): held again
    doc.status = "quarantined"
    again = await hold_library_doc(
        session, doc, job_id=os.urandom(16).hex(), quarantine_dir=qdir, reasons=["x"],
        chat_id=OWNER,
    )  # fmt: skip
    assert await release(session, again.id, gate=None, now=NOW) == "rejected"
    await session.refresh(again)
    await session.refresh(doc)
    assert again.released_at is None and doc.status == "quarantined"


async def test_release_drops_old_parts_and_chapters(session: AsyncSession, tmp_path: Path) -> None:
    from sqlalchemy import select

    from techradar.db.models import LibraryChapter, LibraryPart

    doc, item = await _held_doc(session, tmp_path / "q")
    session.add(LibraryPart(doc_id=doc.id, ordinal=1, status="done", attempts=0))
    session.add(LibraryChapter(doc_id=doc.id, ordinal=1, title="c", text_path="text/x/01.md"))
    await session.flush()
    assert await release(session, item.id, gate=None, now=NOW) == "released"
    for model in (LibraryPart, LibraryChapter):
        rows = (await session.execute(select(model.id).where(model.doc_id == doc.id))).all()
        assert rows == []


async def test_release_of_a_quarantined_doc_only(session: AsyncSession, tmp_path: Path) -> None:
    doc, item = await _held_doc(session, tmp_path / "q")
    doc.status = "rejected"
    await session.flush()
    assert await release(session, item.id, gate=None, now=NOW) == "rejected"
    await session.refresh(item)
    assert item.released_at is None and await doc_flagged(session, doc.id) is False


async def _held_news(session: AsyncSession, qdir: Path) -> QuarantineItem:
    job_id = os.urandom(16).hex()
    held = qdir / job_id / f"{os.urandom(32).hex()}.html"
    held.parent.mkdir(parents=True)
    held.write_text("<p>hi</p>")
    item = QuarantineItem(job_id=job_id, path=str(held), origin="fetch", reasons=["x"])
    session.add(item)
    await session.flush()
    return item


async def test_other_held_files_need_a_gate(session: AsyncSession, tmp_path: Path) -> None:
    item = await _held_news(session, tmp_path / "q")
    assert await release(session, item.id, gate=None, now=NOW) == "failed"
    await session.refresh(item)
    assert item.released_at is None


async def test_release_refuses_a_gate_that_still_quarantines(
    session: AsyncSession, tmp_path: Path
) -> None:
    item = await _held_news(session, tmp_path / "q")

    async def ignores_release(_item: QuarantineItem) -> ParseResult:
        return ParseResult(job_id=_item.job_id, kind="page", status="quarantined")

    assert await release(session, item.id, gate=ignores_release, now=NOW) == "failed"
    await session.refresh(item)
    assert item.released_at is None


async def test_other_held_files_reject_stays_reject(session: AsyncSession, tmp_path: Path) -> None:
    item = await _held_news(session, tmp_path / "q")

    async def rejects(_item: QuarantineItem) -> ParseResult:
        return ParseResult(job_id=_item.job_id, kind="page", status="rejected")

    assert await release(session, item.id, gate=rejects, now=NOW) == "rejected"
    await session.refresh(item)
    assert item.released_at is None


async def test_delete_item_removes_file_and_is_idempotent(
    session: AsyncSession, tmp_path: Path
) -> None:
    qdir = tmp_path / "q"
    _doc, item = await _held_doc(session, qdir)
    held = Path(item.path)
    assert await delete_item(session, item.id, quarantine_dir=qdir, now=NOW) == "deleted"
    assert not _exists(held)
    await session.refresh(item)
    assert item.deleted_at is not None
    assert await delete_item(session, item.id, quarantine_dir=qdir, now=NOW) == "already"
    assert await delete_item(session, -1, quarantine_dir=qdir, now=NOW) == "not_found"


async def test_delete_never_touches_the_library(session: AsyncSession, tmp_path: Path) -> None:
    # The bot runs delete_item and has no library mount: the original stays until
    # worker-bulk's purge_deleted_held_docs removes it.
    qdir, lib = tmp_path / "q", tmp_path / "library"
    doc, item = await _held_doc(session, qdir)
    original = _original(lib, doc)
    assert await delete_item(session, item.id, quarantine_dir=qdir, now=NOW) == "deleted"
    assert _exists(original) and not _exists(Path(item.path))


def _original(lib: Path, doc: LibraryDoc, data: bytes = b"macro docx") -> Path:
    original = lib / doc.original_path
    original.parent.mkdir(parents=True, exist_ok=True)
    original.write_bytes(data)
    return original


async def _purge(session: AsyncSession, lib: Path) -> list[int]:
    return await purge_deleted_held_docs(session, library_dir=lib)


async def _gone(session: AsyncSession, doc_id: int) -> bool:
    found = await session.execute(select(LibraryDoc.id).where(LibraryDoc.id == doc_id))
    return found.first() is None


async def test_purge_removes_the_original_of_a_deleted_held_doc(
    session: AsyncSession, tmp_path: Path
) -> None:
    qdir, lib = tmp_path / "q", tmp_path / "library"
    doc, item = await _held_doc(session, qdir)
    original = _original(lib, doc)
    doc_id = doc.id
    assert doc_id not in await _purge(session, lib)  # still held
    assert _exists(original)
    assert await delete_item(session, item.id, quarantine_dir=qdir, now=NOW) == "deleted"
    assert doc_id in await _purge(session, lib)
    assert not _exists(original) and await _gone(session, doc_id)
    assert doc_id not in await _purge(session, lib)  # gone: idempotent


async def test_purge_removes_every_row_of_the_doc(session: AsyncSession, tmp_path: Path) -> None:
    # Nothing of a deleted or expired held doc stays: its original, its row, the rows that
    # hang off it and its held-item rows. A starter pack item only loses the link.
    qdir, lib = tmp_path / "q", tmp_path / "library"
    doc, item = await _held_doc(session, qdir)
    _original(lib, doc)
    pack = StarterPack(name="tstq" + os.urandom(4).hex(), exam="bank", approved=True)
    session.add(pack)
    await session.flush()
    pitem = StarterPackItem(
        pack_id=pack.id,
        url="https://ncert.nic.in/a.pdf",
        title="t",
        kind="pdf",
        licence="l",
        status="downloaded",
        doc_id=doc.id,
    )
    part = LibraryPart(doc_id=doc.id, ordinal=0, status="failed")
    chapter = LibraryChapter(doc_id=doc.id, ordinal=1, title="c", text_path="text/x/01.md")
    session.add_all([pitem, part, chapter])
    await session.flush()
    session.add(BookEval(doc_id=doc.id, question="q?", expected_chunk_ids=[]))
    session.add(
        Chunk(
            doc_path=f"library/{doc.id}/01.md",
            doc_kind="library",
            title="t",
            ordinal=1,
            text="x",
            lang="en",
            content_hash=os.urandom(32).hex(),
            doc_id=doc.id,
            chapter_id=chapter.id,
        )
    )
    await session.flush()
    doc_id, item_id = doc.id, item.id
    assert await delete_item(session, item_id, quarantine_dir=qdir, now=NOW) == "deleted"
    assert doc_id in await _purge(session, lib)
    assert await _gone(session, doc_id)
    for model in (LibraryPart, LibraryChapter, BookEval):
        rows = await session.execute(select(model.id).where(model.doc_id == doc_id))
        assert rows.first() is None, model.__name__
    chunks = await session.execute(
        select(Chunk.id).where(Chunk.doc_kind == "library", Chunk.doc_id == doc_id)
    )
    assert chunks.first() is None
    held = await session.execute(select(QuarantineItem.id).where(QuarantineItem.id == item_id))
    assert held.first() is None
    await session.refresh(pitem)
    assert pitem.doc_id is None and pitem.status == "downloaded"  # never downloaded again


async def test_an_expired_held_doc_is_purged_like_a_deleted_one(
    session: AsyncSession, tmp_path: Path
) -> None:
    # Retention expires the held copy (deleted_at, cleanup_retention); worker-bulk then
    # removes the original and the rows.
    qdir, lib = tmp_path / "q", tmp_path / "library"
    doc, item = await _held_doc(session, qdir)
    original = _original(lib, doc)
    doc_id = doc.id
    item.deleted_at = NOW  # what retention does after expires_at
    await session.flush()
    assert doc_id in await _purge(session, lib)
    assert not _exists(original) and await _gone(session, doc_id)


async def test_the_same_book_can_be_added_again_after_a_purge(
    session: AsyncSession, tmp_path: Path
) -> None:
    # The old row no longer says "Already in your library", and a release the owner once
    # gave to these bytes is not inherited by the new copy.
    qdir, lib = tmp_path / "q", tmp_path / "library"
    doc, item = await _held_doc(session, qdir)
    _original(lib, doc)
    sha, path, name = doc.sha256, doc.original_path, Path(doc.original_path).name
    session.add(
        QuarantineItem(
            job_id=os.urandom(16).hex(),
            path=str(qdir / "old" / name),
            origin="library",
            reasons=["macros"],
            released_at=NOW,
        )
    )
    assert await delete_item(session, item.id, quarantine_dir=qdir, now=NOW) == "deleted"
    assert doc.id in await _purge(session, lib)
    again = LibraryDoc(
        sha256=sha,
        title="Macro Book",
        kind="docx",
        origin="library",
        original_path=path,
        size_bytes=1000,
        status="queued",
        trust="my_own",
    )
    session.add(again)
    await session.flush()  # no unique clash on sha256
    assert await doc_released(session, again) is False


async def test_purge_keeps_the_original_of_a_doc_that_is_not_held(
    session: AsyncSession, tmp_path: Path
) -> None:
    qdir, lib = tmp_path / "q", tmp_path / "library"
    doc, item = await _held_doc(session, qdir)
    original = _original(lib, doc, b"book")
    assert await delete_item(session, item.id, quarantine_dir=qdir, now=NOW) == "deleted"
    doc.status = "processing"  # e.g. another copy of it is being read
    await session.flush()
    assert doc.id not in await _purge(session, lib)
    assert _exists(original) and not await _gone(session, doc.id)


async def test_purge_keeps_the_original_while_another_held_copy_is_live(
    session: AsyncSession, tmp_path: Path
) -> None:
    # A second held copy (another job of the same doc) can still be released, and a release
    # re-reads the original: it stays until every held copy is deleted.
    qdir, lib = tmp_path / "q", tmp_path / "library"
    doc, item = await _held_doc(session, qdir)
    original = _original(lib, doc)
    job2 = os.urandom(16).hex()
    held2 = qdir / job2 / Path(doc.original_path).name
    held2.parent.mkdir(parents=True)
    held2.write_bytes(b"copy")
    item2 = await hold_library_doc(
        session, doc, job_id=job2, quarantine_dir=qdir, reasons=["macros"], chat_id=None
    )
    assert await delete_item(session, item.id, quarantine_dir=qdir, now=NOW) == "deleted"
    assert doc.id not in await _purge(session, lib)
    assert _exists(original)
    assert await delete_item(session, item2.id, quarantine_dir=qdir, now=NOW) == "deleted"
    assert doc.id in await _purge(session, lib)
    assert not _exists(original)


async def test_purge_never_follows_a_stored_path_outside_originals(
    session: AsyncSession, tmp_path: Path
) -> None:
    qdir, lib = tmp_path / "q", tmp_path / "library"
    doc, item = await _held_doc(session, qdir)
    book = lib / "text" / Path(doc.original_path).name
    book.parent.mkdir(parents=True)
    book.write_bytes(b"my book")
    assert await delete_item(session, item.id, quarantine_dir=qdir, now=NOW) == "deleted"
    doc.original_path = f"text/{Path(doc.original_path).name}"
    await session.flush()
    assert doc.id not in await _purge(session, lib)
    assert book.read_bytes() == b"my book"
    assert not await _gone(session, doc.id)  # refused: everything is kept (and logged)


async def test_purge_never_follows_a_linked_originals_folder(
    session: AsyncSession, tmp_path: Path
) -> None:
    qdir, lib = tmp_path / "q", tmp_path / "library"
    doc, item = await _held_doc(session, qdir)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    victim = elsewhere / Path(doc.original_path).name
    victim.write_bytes(b"keep")
    lib.mkdir()
    (lib / "originals").symlink_to(elsewhere, target_is_directory=True)
    assert await delete_item(session, item.id, quarantine_dir=qdir, now=NOW) == "deleted"
    assert doc.id not in await _purge(session, lib)
    assert victim.read_bytes() == b"keep" and not await _gone(session, doc.id)


async def test_delete_item_refuses_path_outside_quarantine(
    session: AsyncSession, tmp_path: Path
) -> None:
    book = tmp_path / "library" / "originals" / "book.pdf"
    book.parent.mkdir(parents=True)
    book.write_bytes(b"my book")
    item = QuarantineItem(
        job_id=os.urandom(16).hex(), path=str(book), origin="library", reasons=["x"]
    )
    session.add(item)
    await session.flush()
    outcome = await delete_item(session, item.id, quarantine_dir=tmp_path / "q", now=NOW)
    assert outcome == "refused"
    assert book.read_bytes() == b"my book"
    await session.refresh(item)
    assert item.deleted_at is None


async def test_list_shows_doc_title_and_hides_released(
    session: AsyncSession, tmp_path: Path
) -> None:
    qdir = tmp_path / "q"
    _doc, item = await _held_doc(session, qdir)
    rows = await list_quarantine(session)
    assert any(r.id == item.id and r.name == "Macro Book" for r in rows)
    await release(session, item.id, gate=Gate(qdir), now=NOW)
    assert all(r.id != item.id for r in await list_quarantine(session))


async def test_hold_library_doc_is_idempotent_and_notifies(
    session: AsyncSession, tmp_path: Path
) -> None:
    from sqlalchemy import select

    from techradar.db.models import Outbox

    doc, item = await _held_doc(session, tmp_path / "q")
    again = await hold_library_doc(
        session,
        doc,
        job_id=item.job_id,
        quarantine_dir=tmp_path / "q",
        reasons=["macros"],
        chat_id=OWNER,
    )
    assert again.id == item.id
    texts = (
        (
            await session.execute(
                select(Outbox.text).where(Outbox.purpose == "quarantine", Outbox.chat_id == OWNER)
            )
        )
        .scalars()
        .all()
    )
    expected = "🔒 Held for review: Macro Book (macros). Use /quarantine to release or delete it."
    assert texts.count(expected) == 1
