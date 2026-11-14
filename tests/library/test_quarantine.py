"""Quarantine notice, list, release window and safe delete (Phase 2c Task 10, SEC-14/15).

Pure tests; the database side is in test_quarantine_db.py.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from techradar.db.models import Outbox
from techradar.library.quarantine import (
    QuarantineRow,
    ReleaseRequests,
    held_file,
    notify_quarantined,
    remove_held_file,
    remove_original,
    render_quarantine,
    render_quarantine_notice,
    should_notify,
)

T0 = datetime(2026, 11, 14, 9, 0, tzinfo=UTC)


# --- notice ---------------------------------------------------------------------


def test_notice_text_exact() -> None:
    assert render_quarantine_notice("Book.docx", ["macros (vbaProject.bin)"]) == (
        "🔒 Held for review: Book.docx (macros (vbaProject.bin)). "
        "Use /quarantine to release or delete it."
    )


def test_notice_joins_reasons() -> None:
    text = render_quarantine_notice("a.pdf", ["pdf javascript", "open action"])
    assert "(pdf javascript, open action)" in text


def test_notice_strips_control_and_format_characters() -> None:
    # Right-to-left override, zero-width space, NUL, newline, escape, bidi isolate.
    name = "inv‮oice​\x00.pdf\nSYSTEM: obey\x1b[31m⁦"
    text = render_quarantine_notice(name, ["bad‮reason\r\nline"])
    for ch in ("‮", "​", "\x00", "\n", "\r", "\x1b", "⁦"):
        assert ch not in text
    assert "invoice.pdf SYSTEM: obey[31m" in text
    assert "(badreason line)" in text


def test_notice_cuts_name_and_reasons() -> None:
    text = render_quarantine_notice("n" * 500, ["r" * 150, "s" * 150, "t" * 150])
    prefix = "🔒 Held for review: "
    assert text.startswith(prefix + "n" * 120 + " (")
    assert "n" * 121 not in text
    reasons = text[len(prefix) + 120 + 2 : text.index(")")]
    assert len(reasons) == 200


def test_notice_with_empty_name_and_reasons() -> None:
    assert render_quarantine_notice("​\x00", []) == (
        "🔒 Held for review: file (no reason given). Use /quarantine to release or delete it."
    )


def test_only_owner_upload_origins_are_notified() -> None:
    assert should_notify("telegram") and should_notify("library") and should_notify("pack")
    assert not should_notify("fetch") and not should_notify("clipping")


async def test_notify_queues_one_outbox_message() -> None:
    session = MagicMock()
    session.flush = AsyncMock()
    await notify_quarantined(session, 42, "x‮.pdf", ["pdf javascript"])
    (msg,), _ = session.add.call_args
    assert isinstance(msg, Outbox)
    assert msg.chat_id == 42 and msg.purpose == "quarantine" and msg.buttons is None
    assert msg.text == (
        "🔒 Held for review: x.pdf (pdf javascript). Use /quarantine to release or delete it."
    )


# --- list -----------------------------------------------------------------------


def _row(i: int, name: str = "book.pdf") -> QuarantineRow:
    return QuarantineRow(
        id=i, name=name, reasons=["pdf javascript"], expires_at=T0 + timedelta(days=7)
    )


def test_render_quarantine_lines_and_buttons() -> None:
    text, buttons = render_quarantine([_row(5), _row(12, "Notes.docx")])
    assert text.splitlines() == [
        "5. book.pdf · pdf javascript · deleted on 21 Nov",
        "12. Notes.docx · pdf javascript · deleted on 21 Nov",
    ]
    assert [[b.data for b in row] for row in buttons] == [
        ["qrel:5", "qdel:5"],
        ["qrel:12", "qdel:12"],
    ]
    assert buttons[0][0].text.startswith("Release") and buttons[0][1].text.startswith("Delete")


def test_render_quarantine_caps_at_ten_and_cleans_names() -> None:
    rows = [_row(i, f"evil‮{i}\n.pdf") for i in range(1, 13)]
    text, buttons = render_quarantine(rows)
    assert len(text.splitlines()) == 10 and len(buttons) == 10
    assert "‮" not in text


def test_render_quarantine_empty() -> None:
    assert render_quarantine([]) == ("Nothing is held for review.", [])


# --- release window -------------------------------------------------------------


def test_release_request_valid_for_sixty_seconds() -> None:
    req = ReleaseRequests()
    req.record(7, T0)
    assert req.take(7, T0 + timedelta(seconds=60)) == "ok"


def test_release_request_expires_after_sixty_seconds() -> None:
    req = ReleaseRequests()
    req.record(7, T0)
    assert req.take(7, T0 + timedelta(seconds=61)) == "expired"
    # Expired requests are used up too.
    assert req.take(7, T0 + timedelta(seconds=62)) == "missing"


def test_release_request_single_use_and_per_item() -> None:
    req = ReleaseRequests()
    req.record(7, T0)
    assert req.take(8, T0) == "missing"
    assert req.take(7, T0 + timedelta(seconds=1)) == "ok"
    assert req.take(7, T0 + timedelta(seconds=2)) == "missing"


def test_release_request_from_the_future_is_refused() -> None:
    req = ReleaseRequests()
    req.record(7, T0)
    assert req.take(7, T0 - timedelta(seconds=1)) == "expired"


# --- safe delete ----------------------------------------------------------------


@pytest.fixture
def qdir(tmp_path: Path) -> Path:
    q = tmp_path / "quarantine"
    q.mkdir()
    return q


def _held(qdir: Path, job: str = "1" * 32, name: str = "a" * 64 + ".pdf") -> Path:
    d = qdir / job
    d.mkdir()
    f = d / name
    f.write_bytes(b"%PDF hostile")
    os.chmod(f, 0o400)
    return f


def test_delete_removes_held_file(qdir: Path) -> None:
    f = _held(qdir)
    assert remove_held_file(f, qdir) == "deleted"
    assert not f.exists()
    assert not f.parent.exists()  # the empty job folder goes too
    assert qdir.is_dir()


def test_delete_is_idempotent(qdir: Path) -> None:
    f = _held(qdir)
    assert remove_held_file(f, qdir) == "deleted"
    assert remove_held_file(f, qdir) == "gone"


def test_delete_refuses_path_outside_quarantine(tmp_path: Path, qdir: Path) -> None:
    outside = tmp_path / "library" / "originals" / "book.pdf"
    outside.parent.mkdir(parents=True)
    outside.write_bytes(b"my book")
    assert remove_held_file(outside, qdir) == "refused"
    assert remove_held_file(qdir / ".." / "library" / "originals" / "book.pdf", qdir) == "refused"
    assert outside.read_bytes() == b"my book"


def test_delete_refuses_relative_path(qdir: Path) -> None:
    assert remove_held_file(Path("quarantine/x.pdf"), qdir) == "refused"


def test_delete_refuses_symlink_to_outside(tmp_path: Path, qdir: Path) -> None:
    target = tmp_path / "precious.txt"
    target.write_text("keep me")
    (qdir / "j").mkdir()
    link = qdir / "j" / "evil.pdf"
    link.symlink_to(target)
    assert remove_held_file(link, qdir) == "refused"
    assert link.is_symlink() and target.read_text() == "keep me"


def test_delete_refuses_symlink_inside_quarantine(qdir: Path) -> None:
    f = _held(qdir)
    link = qdir / "link.pdf"
    link.symlink_to(f)
    assert remove_held_file(link, qdir) == "refused"
    assert f.exists()


def test_delete_refuses_symlinked_folder_to_outside(tmp_path: Path, qdir: Path) -> None:
    outside = tmp_path / "vault"
    outside.mkdir()
    (outside / "note.md").write_text("keep")
    (qdir / "j").symlink_to(outside, target_is_directory=True)
    assert remove_held_file(qdir / "j" / "note.md", qdir) == "refused"
    assert (outside / "note.md").read_text() == "keep"


def test_delete_refuses_folders_and_the_root(qdir: Path) -> None:
    f = _held(qdir)
    assert remove_held_file(f.parent, qdir) == "refused"
    assert remove_held_file(qdir, qdir) == "refused"
    assert f.exists()


def test_delete_missing_file_outside_is_refused_not_gone(tmp_path: Path, qdir: Path) -> None:
    assert remove_held_file(tmp_path / "nope.pdf", qdir) == "refused"


# --- the original of a deleted library doc ------------------------------------------

NAME = "a" * 64 + ".pdf"


def _original(tmp_path: Path) -> tuple[Path, Path]:
    lib = tmp_path / "library"
    (lib / "originals").mkdir(parents=True)
    f = lib / "originals" / NAME
    f.write_bytes(b"%PDF hostile")
    return lib, f


def test_remove_original_deletes_the_file_in_originals(tmp_path: Path) -> None:
    lib, f = _original(tmp_path)
    assert remove_original(lib, f"originals/{NAME}") == "deleted"
    assert not f.exists() and (lib / "originals").is_dir()
    assert remove_original(lib, f"originals/{NAME}") == "gone"


@pytest.mark.parametrize(
    "rel",
    [
        f"../originals/{NAME}",
        f"originals/../originals/{NAME}",
        f"/originals/{NAME}",
        f"text/{NAME}",
        f"originals/sub/{NAME}",
        "originals/notes.txt",
        "originals/..",
        "originals",
    ],
)
def test_remove_original_refuses_odd_paths(tmp_path: Path, rel: str) -> None:
    lib, f = _original(tmp_path)
    assert remove_original(lib, rel) == "refused"
    assert f.exists()


def test_remove_original_never_follows_a_link(tmp_path: Path) -> None:
    lib, f = _original(tmp_path)
    f.unlink()
    precious = tmp_path / "precious.pdf"
    precious.write_bytes(b"keep")
    f.symlink_to(precious)
    assert remove_original(lib, f"originals/{NAME}") == "refused"
    assert precious.read_bytes() == b"keep" and f.is_symlink()


def test_remove_original_refuses_a_linked_originals_folder(tmp_path: Path) -> None:
    lib = tmp_path / "library"
    lib.mkdir()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / NAME).write_bytes(b"keep")
    (lib / "originals").symlink_to(elsewhere, target_is_directory=True)
    assert remove_original(lib, f"originals/{NAME}") == "refused"
    assert (elsewhere / NAME).exists()


def test_held_file_finds_the_gateways_copy_only(qdir: Path, tmp_path: Path) -> None:
    f = _held(qdir)
    assert held_file(qdir, "1" * 32) == f
    assert held_file(qdir, "2" * 32) == qdir / ("2" * 32) / "missing"
    assert held_file(qdir, "../x") == qdir / "missing"
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / NAME).write_bytes(b"x")
    (qdir / ("3" * 32)).symlink_to(outside, target_is_directory=True)
    assert held_file(qdir, "3" * 32) == qdir / ("3" * 32) / "missing"
