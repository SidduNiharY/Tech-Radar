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
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from techradar.db.engine import make_engine
from techradar.db.models import LibraryDoc, QuarantineItem
from techradar.intake.av import AvResult
from techradar.intake.gateway import gate_job
from techradar.library.quarantine import (
    ReleaseRequests,
    confirm_release,
    delete_item,
    doc_flagged,
    hold_library_doc,
    list_quarantine,
    release,
    request_release,
)
from techradar.schemas.pipeline import CleanDoc, ParseJob, ParseResult
from techradar.settings import Settings
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


async def test_release_processes_as_flagged(session: AsyncSession, tmp_path: Path) -> None:
    doc, item = await _held_doc(session, tmp_path / "q")
    assert await doc_flagged(session, doc.id) is False
    gate = Gate(tmp_path / "q")
    requests = ReleaseRequests()

    prompt = await request_release(session, item.id, requests=requests, now=NOW)
    assert prompt is not None
    text, buttons = prompt
    assert text == (
        "Release Macro Book? It will be processed as flagged: searchable, "
        "but never used for facts, cards or questions."
    )
    assert [[b.text, b.data] for b in buttons[0]] == [["Yes, release", f"qrel_ok:{item.id}"]]

    outcome = await confirm_release(
        session, item.id, requests=requests, gate=gate, now=NOW + timedelta(seconds=30)
    )
    assert outcome == "released"
    assert gate.calls == 0  # a library doc is gated by the parser when its jobs re-run
    assert await doc_flagged(session, doc.id) is True
    await session.refresh(item)
    await session.refresh(doc)
    assert item.released_at is not None and item.deleted_at is None
    assert doc.status == "queued"  # planned again; its jobs run as owner-released


async def test_release_button_expires(session: AsyncSession, tmp_path: Path) -> None:
    doc, item = await _held_doc(session, tmp_path / "q")
    gate = Gate(tmp_path / "q")
    requests = ReleaseRequests()
    assert await request_release(session, item.id, requests=requests, now=NOW) is not None
    outcome = await confirm_release(
        session, item.id, requests=requests, gate=gate, now=NOW + timedelta(seconds=61)
    )
    assert outcome == "expired"
    assert gate.calls == 0
    assert await doc_flagged(session, doc.id) is False
    await session.refresh(item)
    assert item.released_at is None


async def test_double_confirm_is_a_no_op(session: AsyncSession, tmp_path: Path) -> None:
    _doc, item = await _held_doc(session, tmp_path / "q")
    gate = Gate(tmp_path / "q")
    requests = ReleaseRequests()
    await request_release(session, item.id, requests=requests, now=NOW)
    first = await confirm_release(session, item.id, requests=requests, gate=gate, now=NOW)
    second = await confirm_release(session, item.id, requests=requests, gate=gate, now=NOW)
    assert (first, second) == ("released", "no_request")
    # A new request for a released item is refused, so it cannot be released twice.
    assert await request_release(session, item.id, requests=requests, now=NOW) is None
    assert await release(session, item.id, gate=gate, now=NOW) == "not_found"
    assert gate.calls == 0


async def test_confirm_without_request_is_a_no_op(session: AsyncSession, tmp_path: Path) -> None:
    doc, item = await _held_doc(session, tmp_path / "q")
    gate = Gate(tmp_path / "q")
    outcome = await confirm_release(
        session, item.id, requests=ReleaseRequests(), gate=gate, now=NOW
    )
    assert outcome == "no_request"
    assert gate.calls == 0
    assert await doc_flagged(session, doc.id) is False


async def test_request_for_unknown_or_deleted_item_is_refused(
    session: AsyncSession, tmp_path: Path
) -> None:
    requests = ReleaseRequests()
    assert await request_release(session, -1, requests=requests, now=NOW) is None
    _doc, item = await _held_doc(session, tmp_path / "q")
    assert await delete_item(session, item.id, quarantine_dir=tmp_path / "q", now=NOW) == "deleted"
    assert await request_release(session, item.id, requests=requests, now=NOW) is None
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
