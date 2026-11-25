"""Links, PDFs and pasted text from the owner (Phase 3 Task 3), with attack tests.

SEC: SEC-05, SEC-06, SEC-17, SEC-25, SEC-26, SEC-57.
"""

from __future__ import annotations

import hashlib
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select
from telegram import Document

from techradar.bot import main as bot_main
from techradar.bot.intake import (
    DOC_REFUSED_REPLY,
    LINK_QUEUED_REPLY,
    NOT_ALLOWLISTED_REPLY,
    check_document,
    intake_document,
    intake_link,
    intake_paste,
    paste_html,
)
from techradar.bot.routing import route_update
from techradar.worker.names import OWNER_FILE, OWNER_LINK

OWNER = 42
ALLOWED = frozenset({"pib.gov.in", ".pib.gov.in"})
PDF = b"%PDF-1.7\n1 0 obj << >> endobj\n" + b"x" * 200


def _names(folder: Path) -> list[str]:
    return sorted(p.name for p in folder.iterdir())


def _tree(folder: Path) -> list[str]:
    return sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*"))


class FakeDefer:
    def __init__(self) -> None:
        self.names: list[str] = []

    async def __call__(self, name: str) -> None:
        self.names.append(name)


# --- routing -----------------------------------------------------------------------------


def test_route_link_and_paste() -> None:
    assert route_update(42, "https://pib.gov.in/x", 42).action == "link"
    assert route_update(42, "a " * 150, 42).action == "paste"
    assert route_update(42, "short note", 42).action == "ignore"


@pytest.mark.parametrize(
    "text",
    [
        "javascript:alert(1)",
        "file:///etc/passwd",
        "data:text/html,<script>x</script>",
        "http://pib.gov.in/x",
        "https://127.0.0.1/admin",
        "https://[::1]/x",
        "https://evil.example/a",
    ],
)
def test_dangerous_links_are_routed_so_they_get_a_refusal(text: str) -> None:
    assert route_update(42, text, 42).action == "link"


def test_links_and_pastes_from_strangers_or_groups_are_ignored() -> None:
    assert route_update(7, "https://pib.gov.in/x", 42).action == "ignore"
    assert route_update(7, "a " * 150, 42).action == "ignore"
    assert route_update(-100, "https://pib.gov.in/x", 42, frozenset({-100})).action == "ignore"
    assert route_update(-100, "a " * 150, 42, frozenset({-100})).action == "ignore"


def test_long_text_with_a_url_is_not_a_paste() -> None:
    assert route_update(42, "word " * 50 + "https://pib.gov.in/x", 42).action == "ignore"
    assert route_update(42, "two links https://a.in https://b.in", 42).action == "ignore"


# --- intake_link: allowlist only, nothing fetched -----------------------------------------


@pytest.mark.parametrize(
    ("url", "reply"),
    [
        ("https://evil.example/a", NOT_ALLOWLISTED_REPLY),
        ("https://pib.gov.in.evil.example/a", NOT_ALLOWLISTED_REPLY),
        ("javascript:alert(1)", "That link can't be used (scheme)."),
        ("file:///etc/passwd", "That link can't be used (scheme)."),
        ("http://pib.gov.in/x", "That link can't be used (scheme)."),
        ("https://127.0.0.1/x", "That link can't be used (ip_literal)."),
        ("https://[::1]/x", "That link can't be used (ip_literal)."),
        ("https://user:pw@pib.gov.in/x", "That link can't be used (userinfo)."),
        ("https://pib.gov.in:8443/x", "That link can't be used (port)."),
        ("https://pib.gov.in/" + "a" * 2100, "That link can't be used (too_long)."),
    ],
)
async def test_refused_links_never_touch_the_database(url: str, reply: str) -> None:
    session = MagicMock()
    session.execute = AsyncMock()
    assert await intake_link(session, url, ALLOWED) == reply
    session.execute.assert_not_called()
    session.add.assert_not_called()


@pytest.mark.db
async def test_link_not_allowlisted_reply(session: Any) -> None:
    reply = await intake_link(session, "https://evil.example/a", frozenset({"pib.gov.in"}))
    assert reply.startswith("That site isn't on the allowlist")


@pytest.mark.db
async def test_link_allowlisted_queues_raw_item(session: Any) -> None:
    from techradar.db.models import RawItem

    url = "https://PIB.gov.in/PressRelease.aspx?id=1&t=intake-test"
    assert await intake_link(session, url, ALLOWED) == LINK_QUEUED_REPLY
    clean = "https://pib.gov.in/PressRelease.aspx?id=1&t=intake-test"
    row = (await session.execute(select(RawItem).where(RawItem.url == clean))).scalar_one()
    assert row.source_id == 0 and row.status == "new" and row.kind == "page"
    assert row.url_hash == hashlib.sha256(clean.encode()).hexdigest()
    # The same link twice is one row.
    assert await intake_link(session, url, ALLOWED) == LINK_QUEUED_REPLY
    rows = (await session.execute(select(RawItem).where(RawItem.url == clean))).scalars().all()
    assert len(rows) == 1


# --- pasted text --------------------------------------------------------------------------


async def test_paste_is_escaped_and_queued(tmp_path: Path) -> None:
    defer = FakeDefer()
    reply = await intake_paste("<script>x</script> " + "word " * 60, tmp_path / "in", defer)
    assert reply == "Queued."
    raw = next((tmp_path / "in").iterdir()).read_text()
    assert "<script>" not in raw and "&lt;script&gt;" in raw
    assert defer.names == [next((tmp_path / "in").iterdir()).name]


def test_paste_drops_control_characters_and_keeps_paragraphs() -> None:
    page = paste_html("first\u0000 para‮\n\nsecond <b>para</b>").decode()
    assert "\u0000" not in page and "‮" not in page
    assert "<p>first para</p>" in page and "<p>second &lt;b&gt;para&lt;/b&gt;</p>" in page


async def test_paste_into_a_planted_symlink_folder_is_refused(tmp_path: Path) -> None:
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (tmp_path / "in").symlink_to(elsewhere)
    defer = FakeDefer()
    assert await intake_paste("word " * 60, tmp_path / "in", defer) == "Couldn't save that file."
    assert defer.names == [] and list(elsewhere.iterdir()) == []


# --- documents ----------------------------------------------------------------------------


async def test_document_rejects_non_pdf_and_big(tmp_path: Path) -> None:
    defer = FakeDefer()
    assert await intake_document(b"x", "image/png", tmp_path, defer) == DOC_REFUSED_REPLY
    big = b"%PDF-" + b"x" * 5_000_001
    assert await intake_document(big, "application/pdf", tmp_path, defer) == DOC_REFUSED_REPLY
    assert defer.names == [] and _names(tmp_path) == []


@pytest.mark.parametrize(
    "data", [b"MZ\x90\x00%PDF-1.7", b"\x7fELF%PDF-", b"PK\x03\x04%PDF-", b"<html>not a pdf"]
)
async def test_document_with_a_pdf_label_but_other_bytes_is_refused(
    tmp_path: Path, data: bytes
) -> None:
    defer = FakeDefer()
    assert await intake_document(data, "application/pdf", tmp_path, defer) == DOC_REFUSED_REPLY
    assert defer.names == [] and _names(tmp_path) == []


def test_check_document_before_download() -> None:
    assert check_document("application/pdf", 1000) is None
    assert check_document("application/pdf", 5_000_001) == DOC_REFUSED_REPLY
    assert check_document("application/pdf", None) == DOC_REFUSED_REPLY  # size unknown
    assert check_document("application/x-msdownload", 1000) == DOC_REFUSED_REPLY
    assert check_document(None, 1000) == DOC_REFUSED_REPLY


async def test_pdf_is_saved_privately_by_hash_and_queued(tmp_path: Path) -> None:
    defer = FakeDefer()
    assert await intake_document(PDF, "application/pdf", tmp_path, defer) == "Queued."
    name = hashlib.sha256(PDF).hexdigest() + ".pdf"
    assert defer.names == [name]
    assert (tmp_path / name).stat().st_mode & 0o777 == 0o640


# --- bot handlers -------------------------------------------------------------------------


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> SimpleNamespace:
    s = SimpleNamespace(
        telegram_owner_chat_id=OWNER, data_dir=tmp_path, max_question_chars=500, tz="UTC"
    )
    monkeypatch.setattr(bot_main, "get_settings", lambda: s)
    return s


def _update(
    chat_id: int,
    *,
    text: str | None = None,
    document: Document | None = None,
    user_id: int | None = None,
    download: bytes = PDF,
    tg_size: int | None = None,
    in_dir: Path | None = None,
):
    update = MagicMock()
    update.effective_chat.id = chat_id
    update.effective_user.id = chat_id if user_id is None else user_id
    update.message.text = text
    update.message.document = document
    update.message.reply_to_message = None
    update.message.reply_text = AsyncMock()
    tg_file = MagicMock()
    tg_file.file_size = len(download) if tg_size is None else tg_size
    tg_file.download_as_bytearray = AsyncMock(return_value=bytearray(download))
    context = MagicMock()
    context.bot.get_file = AsyncMock(return_value=tg_file)
    deferrer = SimpleNamespace(defer_async=AsyncMock())
    proc = MagicMock()
    proc.configure_task = MagicMock(return_value=deferrer)

    @asynccontextmanager
    async def factory():
        yield MagicMock()

    context.application.bot_data = {
        "owner_id": OWNER,
        "session_factory": factory,
        "procrastinate_app": proc,
        "owner_in_dir": in_dir,
    }
    return update, context, proc, deferrer, tg_file


def _doc(name: str = "notes.pdf", mime: str = "application/pdf", size: int | None = None):
    return Document("fid", "uid", file_name=name, mime_type=mime, file_size=size or len(PDF))


async def test_owner_pdf_is_downloaded_saved_by_hash_and_queued(
    settings: SimpleNamespace, tmp_path: Path
) -> None:
    in_dir = tmp_path / "telegram-in"
    update, context, proc, deferrer, _f = _update(OWNER, document=_doc(), in_dir=in_dir)
    await bot_main.handle_message(update, context)
    name = hashlib.sha256(PDF).hexdigest() + ".pdf"
    proc.configure_task.assert_called_once_with(name=OWNER_FILE)
    deferrer.defer_async.assert_awaited_once_with(name=name)
    update.message.reply_text.assert_awaited_once_with("Queued.")
    assert [p.name for p in in_dir.iterdir()] == [name]


@pytest.mark.parametrize(
    "file_name",
    ["../../etc/cron.d/x.pdf", "/data/raw/evil.pdf", "..\\..\\x.pdf", "a\x00b.pdf", "x/../../y"],
)
async def test_a_path_in_the_telegram_file_name_is_never_used(
    settings: SimpleNamespace, tmp_path: Path, file_name: str
) -> None:
    in_dir = tmp_path / "telegram-in"
    update, context, _p, deferrer, _f = _update(OWNER, document=_doc(name=file_name), in_dir=in_dir)
    await bot_main.handle_message(update, context)
    name = hashlib.sha256(PDF).hexdigest() + ".pdf"
    deferrer.defer_async.assert_awaited_once_with(name=name)
    assert _tree(tmp_path) == [
        "telegram-in",
        f"telegram-in/{name}",
    ]


async def test_stranger_document_is_never_downloaded(
    settings: SimpleNamespace, tmp_path: Path
) -> None:
    update, context, proc, _d, _f = _update(7, document=_doc(), in_dir=tmp_path / "in")
    await bot_main.handle_message(update, context)
    context.bot.get_file.assert_not_called()
    update.message.reply_text.assert_not_called()
    proc.configure_task.assert_not_called()


async def test_document_from_another_sender_in_the_owner_chat_is_ignored(
    settings: SimpleNamespace, tmp_path: Path
) -> None:
    update, context, proc, _d, _f = _update(
        OWNER, document=_doc(), user_id=999, in_dir=tmp_path / "in"
    )
    await bot_main.handle_message(update, context)
    context.bot.get_file.assert_not_called()
    update.message.reply_text.assert_not_called()


async def test_oversized_document_is_refused_before_download(
    settings: SimpleNamespace, tmp_path: Path
) -> None:
    update, context, proc, _d, _f = _update(
        OWNER, document=_doc(size=5_000_001), in_dir=tmp_path / "in"
    )
    await bot_main.handle_message(update, context)
    context.bot.get_file.assert_not_called()
    update.message.reply_text.assert_awaited_once_with(DOC_REFUSED_REPLY)


async def test_document_with_unknown_size_is_refused_before_download(
    settings: SimpleNamespace, tmp_path: Path
) -> None:
    doc = Document("fid", "uid", file_name="a.pdf", mime_type="application/pdf")
    update, context, _p, _d, _f = _update(OWNER, document=doc, in_dir=tmp_path / "in")
    await bot_main.handle_message(update, context)
    context.bot.get_file.assert_not_called()
    update.message.reply_text.assert_awaited_once_with(DOC_REFUSED_REPLY)


@pytest.mark.parametrize("mime", ["application/x-msdownload", "image/png", "text/html"])
async def test_wrong_mime_is_refused_before_download(
    settings: SimpleNamespace, tmp_path: Path, mime: str
) -> None:
    update, context, _p, _d, _f = _update(OWNER, document=_doc(mime=mime), in_dir=tmp_path)
    await bot_main.handle_message(update, context)
    context.bot.get_file.assert_not_called()
    update.message.reply_text.assert_awaited_once_with(DOC_REFUSED_REPLY)


async def test_file_bigger_than_its_metadata_said_is_refused(
    settings: SimpleNamespace, tmp_path: Path
) -> None:
    in_dir = tmp_path / "in"
    big = b"%PDF-" + b"x" * 5_000_001
    update, context, proc, _d, tg_file = _update(
        OWNER, document=_doc(), download=big, tg_size=100, in_dir=in_dir
    )
    await bot_main.handle_message(update, context)
    update.message.reply_text.assert_awaited_once_with(DOC_REFUSED_REPLY)
    proc.configure_task.assert_not_called()
    assert not in_dir.exists() or list(in_dir.iterdir()) == []


async def test_telegram_file_size_over_the_cap_stops_the_download(
    settings: SimpleNamespace, tmp_path: Path
) -> None:
    update, context, _p, _d, tg_file = _update(
        OWNER, document=_doc(), tg_size=5_000_001, in_dir=tmp_path
    )
    await bot_main.handle_message(update, context)
    tg_file.download_as_bytearray.assert_not_called()
    update.message.reply_text.assert_awaited_once_with(DOC_REFUSED_REPLY)


async def test_symlink_planted_in_the_drop_folder_is_never_followed(
    settings: SimpleNamespace, tmp_path: Path
) -> None:
    in_dir = tmp_path / "telegram-in"
    in_dir.mkdir()
    victim = tmp_path / "victim"
    victim.write_text("keep")
    (in_dir / (hashlib.sha256(PDF).hexdigest() + ".pdf")).symlink_to(victim)
    update, context, proc, _d, _f = _update(OWNER, document=_doc(), in_dir=in_dir)
    await bot_main.handle_message(update, context)
    assert victim.read_text() == "keep"
    proc.configure_task.assert_not_called()
    update.message.reply_text.assert_awaited_once_with("Couldn't save that file.")


async def test_owner_link_defers_the_worker_check(settings: SimpleNamespace) -> None:
    update, context, proc, deferrer, _f = _update(OWNER, text="https://pib.gov.in/x")
    await bot_main.handle_message(update, context)
    proc.configure_task.assert_called_once_with(name=OWNER_LINK)
    deferrer.defer_async.assert_awaited_once_with(url="https://pib.gov.in/x")
    context.bot.get_file.assert_not_called()


async def test_stranger_link_and_paste_get_nothing(settings: SimpleNamespace) -> None:
    for text in ("https://pib.gov.in/x", "word " * 60):
        update, context, proc, _d, _f = _update(7, text=text)
        await bot_main.handle_message(update, context)
        proc.configure_task.assert_not_called()
        update.message.reply_text.assert_not_called()


async def test_owner_paste_is_saved_and_queued(settings: SimpleNamespace, tmp_path: Path) -> None:
    in_dir = tmp_path / "telegram-in"
    update, context, proc, deferrer, _f = _update(OWNER, text="word " * 60, in_dir=in_dir)
    await bot_main.handle_message(update, context)
    (saved,) = list(in_dir.iterdir())
    assert saved.name.endswith(".html")
    proc.configure_task.assert_called_once_with(name=OWNER_FILE)
    deferrer.defer_async.assert_awaited_once_with(name=saved.name)
    update.message.reply_text.assert_awaited_once_with("Queued.")
