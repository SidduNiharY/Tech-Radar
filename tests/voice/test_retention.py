"""Voice audio is checked before decoding and deleted after 24 hours (Phase 6 Tasks 1 and 6).

SEC: SEC-15, SEC-18, SEC-57.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from techradar.voice.jobs import (
    _unlink_file,
    _unlink_reply,
    analyse_voice,
    cleanup_voice,
    mark_voice_unavailable,
)

NOW = datetime(2026, 11, 25, 6, 0, tzinfo=UTC)
OGG = b"OggS\x00\x02" + b"v" * 100
NAME = hashlib.sha256(OGG).hexdigest() + ".ogg"


def _voice_dir(tmp_path: Path) -> Path:
    voice_dir = tmp_path / "voice"
    (voice_dir / "in").mkdir(parents=True)
    (voice_dir / "in" / NAME).write_bytes(OGG)
    return voice_dir


def test_unlink_removes_a_hash_named_note_in_the_voice_folder(tmp_path: Path) -> None:
    voice_dir = _voice_dir(tmp_path)
    _unlink_file(str(voice_dir / "in" / NAME), voice_dir)
    assert not (voice_dir / "in" / NAME).exists()


@pytest.mark.parametrize("where", ["outside", "dotdot", "not_hash"])
def test_unlink_never_removes_a_file_outside_the_voice_folder(tmp_path: Path, where: str) -> None:
    voice_dir = _voice_dir(tmp_path)
    precious = tmp_path / "precious.ogg"
    precious.write_bytes(b"keep")
    path = {
        "outside": str(precious),
        "dotdot": str(voice_dir / "in" / ".." / ".." / "precious.ogg"),
        "not_hash": str(voice_dir / "in" / "precious.ogg"),
    }[where]
    (voice_dir / "in" / "precious.ogg").write_bytes(b"keep")
    _unlink_file(path, voice_dir)
    assert precious.read_bytes() == b"keep"
    assert (voice_dir / "in" / "precious.ogg").exists()


def test_unlink_through_a_symlinked_voice_folder_does_nothing(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    (real / NAME).write_bytes(OGG)
    voice_dir = tmp_path / "voice"
    voice_dir.mkdir()
    (voice_dir / "in").symlink_to(real)
    _unlink_file(str(voice_dir / "in" / NAME), voice_dir)
    assert (real / NAME).exists()


def test_unlink_of_a_planted_symlink_removes_the_link_not_its_target(tmp_path: Path) -> None:
    voice_dir = tmp_path / "voice"
    (voice_dir / "in").mkdir(parents=True)
    target = tmp_path / "target"
    target.write_bytes(b"keep")
    (voice_dir / "in" / NAME).symlink_to(target)
    _unlink_file(str(voice_dir / "in" / NAME), voice_dir)
    assert target.read_bytes() == b"keep"
    assert not (voice_dir / "in" / NAME).is_symlink()


def test_unlink_reply_removes_only_that_sessions_reply(tmp_path: Path) -> None:
    out = tmp_path / "voice" / "out"
    out.mkdir(parents=True)
    (out / "reply_5.ogg").write_bytes(b"x")
    (out / "reply_6.ogg").write_bytes(b"y")
    _unlink_reply(tmp_path / "voice", 5)
    assert sorted(p.name for p in out.iterdir()) == ["reply_6.ogg"]
    _unlink_reply(tmp_path / "missing", 5)  # no folder: nothing to do


class FakeOutbox:
    def __init__(self) -> None:
        self.texts: list[str] = []

    async def send_text(self, text: str, button: Any = None) -> None:
        self.texts.append(text)


# --- database (run on the server) ------------------------------------------------------------


@pytest.mark.db
async def test_analysis_refuses_a_file_that_is_not_a_voice_note(
    session: Any, tmp_path: Path
) -> None:
    from techradar.db.models import VoiceSession

    f = tmp_path / "note.ogg"
    f.write_bytes(b"MZ\x90\x00 an exe renamed")
    row = VoiceSession(source="telegram", duration_s=5.0, status="queued", audio_path=str(f))
    session.add(row)
    await session.flush()
    transcriber = MagicMock()
    outbox = FakeOutbox()
    await analyse_voice(
        session,
        row.id,
        transcriber=transcriber,
        phoneme_model=MagicMock(),
        completer=MagicMock(),
        outbox=outbox,
        probe=lambda _p: "not ogg",
    )
    assert row.status == "failed"
    assert outbox.texts == ["I can only analyse Telegram voice notes."]
    transcriber.transcribe.assert_not_called()  # nothing decoded or transcribed


@pytest.mark.db
async def test_unavailable_analysis_keeps_the_24h_limit(session: Any) -> None:
    from techradar.db.models import VoiceSession

    row = VoiceSession(
        source="telegram",
        duration_s=5.0,
        status="queued",
        audio_path="/data/voice/in/x.ogg",
        delete_after=NOW + timedelta(days=30),
    )
    session.add(row)
    await session.flush()
    assert await mark_voice_unavailable(session, row.id, now=NOW) is True
    assert row.status == "failed" and row.delete_after == NOW + timedelta(hours=24)
    assert await mark_voice_unavailable(session, -1, now=NOW) is False


@pytest.mark.db
async def test_cleanup_deletes_expired_notes_and_replies_unless_kept(
    session: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from techradar.db.models import VoiceSession

    monkeypatch.setattr(session, "commit", session.flush)  # the fixture rolls back
    voice_dir = tmp_path / "voice"
    (voice_dir / "in").mkdir(parents=True)
    (voice_dir / "out").mkdir()
    notes = {}
    for tag in ("expired", "kept", "fresh"):
        data = OGG + tag.encode()
        name = hashlib.sha256(data).hexdigest() + ".ogg"
        (voice_dir / "in" / name).write_bytes(data)
        notes[tag] = voice_dir / "in" / name
    rows = {
        "expired": VoiceSession(
            source="telegram",
            duration_s=5.0,
            status="analysed",
            audio_path=str(notes["expired"]),
            delete_after=NOW - timedelta(hours=1),
        ),
        "kept": VoiceSession(
            source="telegram",
            duration_s=5.0,
            status="analysed",
            audio_path=str(notes["kept"]),
            delete_after=NOW - timedelta(hours=1),
            kept=True,
        ),
        "fresh": VoiceSession(
            source="telegram",
            duration_s=5.0,
            status="queued",
            audio_path=str(notes["fresh"]),
            delete_after=NOW + timedelta(hours=1),
        ),
    }
    session.add_all(rows.values())
    await session.flush()
    (voice_dir / "out" / f"reply_{rows['expired'].id}.ogg").write_bytes(b"r")

    await cleanup_voice(session, now=NOW, voice_dir=voice_dir)
    assert not notes["expired"].exists() and rows["expired"].audio_path is None
    assert not (voice_dir / "out" / f"reply_{rows['expired'].id}.ogg").exists()
    assert notes["kept"].exists() and rows["kept"].audio_path is not None
    assert notes["fresh"].exists() and rows["fresh"].audio_path is not None


@pytest.mark.db
async def test_cleanup_keeps_a_file_another_session_still_needs(
    session: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from techradar.db.models import VoiceSession

    monkeypatch.setattr(session, "commit", session.flush)
    voice_dir = _voice_dir(tmp_path)
    path = str(voice_dir / "in" / NAME)
    old = VoiceSession(
        source="telegram",
        duration_s=5.0,
        status="analysed",
        audio_path=path,
        delete_after=NOW - timedelta(hours=1),
    )
    again = VoiceSession(  # the same note sent again: same hash name
        source="telegram",
        duration_s=5.0,
        status="queued",
        audio_path=path,
        delete_after=NOW + timedelta(hours=20),
    )
    session.add_all([old, again])
    await session.flush()
    await cleanup_voice(session, now=NOW, voice_dir=voice_dir)
    assert old.audio_path is None and (voice_dir / "in" / NAME).exists()


@pytest.mark.db
async def test_cleanup_never_deletes_a_database_path_outside_the_voice_folder(
    session: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from techradar.db.models import VoiceSession

    monkeypatch.setattr(session, "commit", session.flush)
    voice_dir = _voice_dir(tmp_path)
    precious = tmp_path / "precious.txt"
    precious.write_text("keep")
    row = VoiceSession(
        source="telegram",
        duration_s=5.0,
        status="analysed",
        audio_path=str(precious),
        delete_after=NOW - timedelta(hours=1),
    )
    session.add(row)
    await session.flush()
    await cleanup_voice(session, now=NOW, voice_dir=voice_dir)
    assert precious.read_text() == "keep"
