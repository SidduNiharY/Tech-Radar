"""Library inbox intake (Phase 2c Task 2): settling, classifying, storing, deduplicating."""

from __future__ import annotations

import hashlib
import os
import time
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from techradar.db.engine import make_engine
from techradar.db.models import LibraryDoc
from techradar.library.inbox import (
    MIME_TO_KIND,
    InboxFile,
    classify,
    load_limits,
    plan_library_intake,
    stable_files,
)
from techradar.settings import Settings

LIMITS = {
    "library": {
        "pdf": 300_000_000,
        "docx": 50_000_000,
        "epub": 50_000_000,
        "video": 4_000_000_000,
        "audio": 1_000_000_000,
        "html": 5_000_000,
    },
    "pack": {"pdf": 200_000_000, "docx": 50_000_000, "html": 5_000_000},
}
NOW = 2_000_000_000.0
OLD = NOW - 3600


def _old(path: Path, data: bytes = b"%PDF-1.4\nx") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    os.utime(path, (OLD, OLD))
    return path


def _unique_pdf(tag: str) -> bytes:
    return b"%PDF-1.4\n" + tag.encode() + os.urandom(16)


class Recorder:
    def __init__(self) -> None:
        self.texts: list[str] = []
        self.queued: list[int] = []

    async def send(self, text: str) -> None:
        self.texts.append(text)

    async def queue_doc(self, doc_id: int) -> None:
        self.queued.append(doc_id)


# --- stable_files ---------------------------------------------------------------


def test_partial_sync_file_skipped(tmp_path: Path):
    (tmp_path / ".syncthing.book.pdf.tmp").write_bytes(b"x")
    f = tmp_path / "book.pdf"
    f.write_bytes(b"%PDF")
    os.utime(f, (time.time(), time.time()))  # just written
    assert stable_files(tmp_path, time.time()) == []


def test_settled_file_is_returned_with_size_and_mtime(tmp_path: Path):
    f = _old(tmp_path / "book.pdf", b"%PDF-1.4\nabc")
    [got] = stable_files(tmp_path, NOW)
    assert got.path == f and got.size == 12 and got.mtime == OLD
    assert stable_files(tmp_path, OLD + 59) == []
    assert len(stable_files(tmp_path, OLD + 60)) == 1


def test_stable_files_skips_state_folders_dotfiles_and_temp_names(tmp_path: Path):
    _old(tmp_path / "ok.pdf")
    _old(tmp_path / "sub" / "nested.pdf")
    for skipped in (
        "done/a.pdf",
        "rejected/b.pdf",
        "gate/c.pdf",
        ".DS_Store",
        ".hidden.pdf",
        "x.tmp",
        "~syncthing~d.pdf.tmp",
        ".stfolder/e.pdf",
    ):
        _old(tmp_path / skipped)
    names = sorted(f.path.relative_to(tmp_path).as_posix() for f in stable_files(tmp_path, NOW))
    assert names == ["ok.pdf", "sub/nested.pdf"]


def test_stable_files_never_follows_symlinks(tmp_path: Path):
    inbox = tmp_path / "inbox"
    outside = tmp_path / "outside"
    _old(outside / "secret.pdf")
    _old(inbox / "real.pdf")
    (inbox / "link.pdf").symlink_to(outside / "secret.pdf")
    (inbox / "linkdir").symlink_to(outside, target_is_directory=True)
    names = [f.path.name for f in stable_files(inbox, NOW)]
    assert names == ["real.pdf"]


def test_stable_files_missing_inbox_is_empty(tmp_path: Path):
    assert stable_files(tmp_path / "nope", NOW) == []


# --- classify -------------------------------------------------------------------


def test_classify_reasons():
    big = InboxFile(path=Path("b.pdf"), size=301_000_000, mtime=0)
    assert (
        classify(big, "application/pdf", LIMITS, "library").reason
        == "too large (301 MB, limit 300 MB)"
    )
    assert (
        classify(big, "application/zip", LIMITS, "library").reason
        == "unsupported type application/zip"
    )


def test_classify_accepts_and_maps_kind():
    small = InboxFile(path=Path("b.pdf"), size=10, mtime=0)
    d = classify(small, "application/pdf", LIMITS, "library")
    assert d.kind == "pdf" and d.reason is None
    assert classify(small, "video/x-matroska", LIMITS, "library").kind == "video"
    assert classify(small, "audio/x-wav", LIMITS, "library").kind == "audio"


def test_classify_pack_has_its_own_kinds_and_limits():
    small = InboxFile(path=Path("b.epub"), size=10, mtime=0)
    assert classify(small, "application/epub+zip", LIMITS, "pack").reason == (
        "unsupported type application/epub+zip"
    )
    mid = InboxFile(path=Path("b.pdf"), size=250_000_000, mtime=0)
    assert classify(mid, "application/pdf", LIMITS, "library").kind == "pdf"
    assert classify(mid, "application/pdf", LIMITS, "pack").reason == (
        "too large (250 MB, limit 200 MB)"
    )


def test_mime_table_matches_plan():
    assert MIME_TO_KIND["application/pdf"] == "pdf"
    assert MIME_TO_KIND["application/epub+zip"] == "epub"
    assert MIME_TO_KIND["text/html"] == "html"
    assert "application/zip" not in MIME_TO_KIND


def test_real_limits_file_has_library_and_pack_sections():
    limits = load_limits(Path("infra/intake/limits.yaml"))
    assert limits["library"]["pdf"] == 300_000_000 and limits["pack"]["pdf"] == 200_000_000


# --- moving files ---------------------------------------------------------------


class FakeSession:
    """Refusals and file-safety checks never query the database."""

    async def commit(self) -> None:
        pass

    async def rollback(self) -> None:
        pass

    async def execute(self, *a, **k):  # pragma: no cover - must not be reached
        raise AssertionError("database used")


async def _run(inbox: Path, lib: Path, rec: Recorder, **kw) -> list[int]:
    return await plan_library_intake(
        FakeSession(),  # type: ignore[arg-type]
        [(inbox, "library")],
        lib,
        NOW,
        LIMITS,
        queue_doc=rec.queue_doc,
        send=rec.send,
        **kw,
    )


async def test_file_swapped_for_a_symlink_after_the_scan_is_not_followed(tmp_path, monkeypatch):
    # Seen by the Opus review: a swap between scan and copy could copy any file the
    # worker can read (e.g. /run/secrets) into the library.
    inbox = tmp_path / "in"
    book = _old(inbox / "book.html", b"<html><body>x</body></html>")
    secret = tmp_path / "secret.txt"
    secret.write_text("TOKEN")
    import techradar.library.inbox as mod

    real_scan = mod.stable_files

    def scan_then_swap(*a, **k):
        found = real_scan(*a, **k)
        book.unlink()
        book.symlink_to(secret)
        return found

    monkeypatch.setattr(mod, "stable_files", scan_then_swap)
    rec = Recorder()
    assert await _run(inbox, tmp_path / "library", rec) == []
    assert secret.read_text() == "TOKEN" and book.is_symlink()
    assert not (tmp_path / "library" / "originals").exists() or not any(
        (tmp_path / "library" / "originals").iterdir()
    )


async def test_folder_swapped_for_a_symlink_is_not_followed(tmp_path, monkeypatch):
    # A sub-folder replaced by a link to the vault must never let the worker
    # move (and so delete) a vault file.
    inbox = tmp_path / "in"
    _old(inbox / "sub" / "note.bin", b"MZ\x90\x00")
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "note.bin").write_bytes(b"precious")
    import shutil

    import techradar.library.inbox as mod

    real_scan = mod.stable_files

    def scan_then_swap(*a, **k):
        found = real_scan(*a, **k)
        shutil.rmtree(inbox / "sub")
        (inbox / "sub").symlink_to(vault, target_is_directory=True)
        return found

    monkeypatch.setattr(mod, "stable_files", scan_then_swap)
    await _run(inbox, tmp_path / "library", Recorder())
    assert (vault / "note.bin").read_bytes() == b"precious"


async def test_file_replaced_by_another_file_is_skipped(tmp_path, monkeypatch):
    inbox = tmp_path / "in"
    book = _old(inbox / "book.bin", b"MZ\x90\x00")
    import techradar.library.inbox as mod

    real_scan = mod.stable_files

    def scan_then_replace(*a, **k):
        found = real_scan(*a, **k)
        book.unlink()
        _old(book, b"MZ\x90\x00 different file")
        return found

    monkeypatch.setattr(mod, "stable_files", scan_then_replace)
    rec = Recorder()
    await _run(inbox, tmp_path / "library", rec)
    assert book.exists() and rec.texts == []  # left for the next run


async def test_a_rejected_file_in_place_of_the_folder_does_not_stop_the_run(tmp_path):
    # The Opus review reproduced this: a plain file named "rejected" crashed every
    # run and stopped vault indexing with it.
    inbox = tmp_path / "in"
    (inbox).mkdir()
    (inbox / "rejected").write_text("not a folder")
    _old(inbox / "a.bin", b"MZ\x90\x00")
    _old(inbox / "b.bin", b"MZ\x90\x00")
    rec = Recorder()
    assert await _run(inbox, tmp_path / "library", rec) == []  # no exception
    assert (inbox / "a.bin").exists() and (inbox / "b.bin").exists()


async def test_one_failing_file_does_not_stop_the_others(tmp_path, monkeypatch):
    inbox = tmp_path / "in"
    _old(inbox / "a.bin", b"MZ\x90\x00")
    _old(inbox / "b.bin", b"MZ\x90\x00")
    import techradar.library.inbox as mod

    calls = {"n": 0}
    real = mod._take_file

    async def flaky(*a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("disk full")
        return await real(*a, **k)

    monkeypatch.setattr(mod, "_take_file", flaky)
    rec = Recorder()
    await _run(inbox, tmp_path / "library", rec)
    assert len(rec.texts) == 1  # the second file was still handled


async def test_oversized_zip_is_refused_before_its_directory_is_read(tmp_path, monkeypatch):
    inbox = tmp_path / "in"
    f = inbox / "huge.docx"
    f.parent.mkdir(parents=True)
    with f.open("wb") as fh:
        fh.write(b"PK\x03\x04")
        fh.truncate(60_000_000)  # over the 50 MB DOCX/EPUB limit, sparse
    os.utime(f, (OLD, OLD))
    import zipfile

    def never(*a, **k):
        raise AssertionError("zip directory read")

    monkeypatch.setattr(zipfile, "ZipFile", never)
    rec = Recorder()
    await _run(inbox, tmp_path / "library", rec)
    assert rec.texts == ["Couldn't add huge.docx: too large (60 MB, limit 50 MB)."]


async def test_per_run_file_cap(tmp_path):
    inbox = tmp_path / "in"
    for i in range(5):
        _old(inbox / f"f{i}.bin", b"MZ\x90\x00")
    rec = Recorder()
    await _run(inbox, tmp_path / "library", rec, max_files=3)
    assert len(rec.texts) == 3
    assert len(list(inbox.glob("f*.bin"))) == 2  # left for the next run


def test_deep_folders_do_not_crash_the_scan(tmp_path):
    from techradar.library.inbox import MAX_DEPTH

    d = tmp_path / "in"
    for i in range(MAX_DEPTH + 5):
        d = d / f"d{i}"
    _old(d / "deep.pdf")
    assert stable_files(tmp_path / "in", NOW) == []  # beyond the depth limit


# --- plan_library_intake: refusals need no database -----------------------------


async def test_refused_file_goes_to_rejected_without_overwrite(tmp_path: Path):
    inbox = tmp_path / "in"
    bad = _old(inbox / "tool.pdf", b"MZ\x90\x00 not a pdf at all")
    (inbox / "rejected").mkdir()
    (inbox / "rejected" / "tool.pdf").write_bytes(b"earlier refusal")
    rec = Recorder()
    ids = await plan_library_intake(
        FakeSession(),  # type: ignore[arg-type]  # refusals never reach the database
        [(inbox, "library")],
        tmp_path / "library",
        NOW,
        LIMITS,
        queue_doc=rec.queue_doc,
        send=rec.send,
    )
    assert ids == [] and rec.queued == []
    assert not bad.exists()
    assert (inbox / "rejected" / "tool.pdf").read_bytes() == b"earlier refusal"
    assert (inbox / "rejected" / "tool-1.pdf").exists()
    assert len(rec.texts) == 1
    assert rec.texts[0].startswith("Couldn't add tool.pdf: unsupported type ")
    assert rec.texts[0].endswith(".")
    assert not (tmp_path / "library").exists()


async def test_refusal_message_cleans_the_file_name(tmp_path: Path):
    inbox = tmp_path / "in"
    _old(inbox / ("evil\x1b[31m\nname" + "x" * 150 + ".bin"), b"MZ\x90\x00")
    rec = Recorder()
    await plan_library_intake(
        FakeSession(),  # type: ignore[arg-type]
        [(inbox, "library")],
        tmp_path / "library",
        NOW,
        LIMITS,
        queue_doc=rec.queue_doc,
        send=rec.send,
    )
    [msg] = rec.texts
    assert "\x1b" not in msg and "\n" not in msg
    name_part = msg[len("Couldn't add ") : msg.index(": unsupported")]
    assert len(name_part) <= 120


# --- plan_library_intake: database tests ----------------------------------------


@pytest.fixture
def db_settings() -> Settings:
    return Settings(
        telegram_owner_chat_id=1,
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
        # Intake commits per file, so remove what the tests created.
        await s.execute(text("DELETE FROM techradar.library_docs WHERE title LIKE 'tst %'"))
        await s.commit()
    await engine.dispose()


async def _count_docs(session: AsyncSession, sha: str) -> int:
    res = await session.execute(
        select(func.count()).select_from(LibraryDoc).where(LibraryDoc.sha256 == sha)
    )
    return res.scalar_one()


@pytest.mark.db
async def test_duplicate_book_detected(session: AsyncSession, tmp_path: Path):
    data = _unique_pdf("dup")
    sha = hashlib.sha256(data).hexdigest()
    inbox = tmp_path / "in"
    _old(inbox / "tst_My_Book.pdf", data)
    rec = Recorder()
    kwargs = {"queue_doc": rec.queue_doc, "send": rec.send}
    lib = tmp_path / "library"
    first = await plan_library_intake(session, [(inbox, "library")], lib, NOW, LIMITS, **kwargs)
    assert len(first) == 1

    _old(inbox / "tst_copy_of_book.pdf", data)  # the same PDF again, under another name
    second = await plan_library_intake(session, [(inbox, "library")], lib, NOW, LIMITS, **kwargs)
    assert second == []
    assert await _count_docs(session, sha) == 1
    assert rec.texts[-1].startswith("Already in your library: ")
    assert "My Book" in rec.texts[-1]
    assert (inbox / "done" / "tst_copy_of_book.pdf").exists()
    assert rec.queued == first


@pytest.mark.db
async def test_original_stored_read_only_outside_raw(session: AsyncSession, tmp_path: Path):
    inbox = tmp_path / "in"
    _old(inbox / "tst_book.pdf", _unique_pdf("ro"))
    rec = Recorder()
    [doc_id] = await plan_library_intake(
        session,
        [(inbox, "library")],
        tmp_path / "library",
        NOW,
        LIMITS,
        queue_doc=rec.queue_doc,
        send=rec.send,
    )
    f = next((tmp_path / "library" / "originals").iterdir())
    assert f.stat().st_mode & 0o777 == 0o440 and not (tmp_path / "raw").exists()
    assert rec.queued == [doc_id]


@pytest.mark.db
async def test_pdf_named_exe_is_stored_as_pdf_and_recorded(session: AsyncSession, tmp_path: Path):
    data = _unique_pdf("exe")
    sha = hashlib.sha256(data).hexdigest()
    inbox = tmp_path / "in"
    _old(inbox / "tst_Polity\x07_Laxmikanth_7th.exe", data)
    rec = Recorder()
    [doc_id] = await plan_library_intake(
        session,
        [(inbox, "library")],
        tmp_path / "library",
        NOW,
        LIMITS,
        queue_doc=rec.queue_doc,
        send=rec.send,
    )
    assert (tmp_path / "library" / "originals" / f"{sha}.pdf").exists()
    doc = (await session.execute(select(LibraryDoc).where(LibraryDoc.id == doc_id))).scalar_one()
    assert doc.kind == "pdf" and doc.origin == "library" and doc.trust == "my_own"
    assert doc.status == "queued" and doc.title == "tst Polity Laxmikanth 7th"
    assert doc.original_path == f"originals/{sha}.pdf"
    assert doc.size_bytes == len(data)
