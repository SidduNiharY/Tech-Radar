"""Voice audio is checked before decoding and deleted after 24 hours (Phase 6 Tasks 1 and 6).

Covers the failure paths of the analysis job (every one sets `delete_after`), the Keep button,
and the hourly cleanup, which removes only hash-named notes in voice/in and our replies in
voice/out, never through a link and never a file another session still needs.

SEC: SEC-15, SEC-18, SEC-57.
"""

from __future__ import annotations

import hashlib
import unittest.mock
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import numpy as np
import pytest

from techradar.voice.jobs import analyse_voice
from techradar.voice.retention import (
    _unlink_file,
    _unlink_reply,
    cleanup_voice,
    keep_voice,
    mark_voice_unavailable,
)
from techradar.voice.transcribe import Transcript
from tests.fakes import FakeCompleter, FakePhonemeModel, FakeTranscriber

NOW = datetime(2026, 11, 25, 6, 0, tzinfo=UTC)
OGG = b"OggS\x00\x02" + b"v" * 100
NAME = hashlib.sha256(OGG).hexdigest() + ".ogg"


def _voice_dir(tmp_path: Path) -> Path:
    voice_dir = tmp_path / "voice"
    (voice_dir / "in").mkdir(parents=True)
    (voice_dir / "in" / NAME).write_bytes(OGG)
    return voice_dir


def _note(voice_dir: Path, tag: str) -> Path:
    """A hash-named note in voice_dir/in, as intake stores it."""
    data = OGG + tag.encode()
    path = voice_dir / "in" / (hashlib.sha256(data).hexdigest() + ".ogg")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


class FakeOutbox:
    def __init__(self) -> None:
        self.texts: list[str] = []
        self.voices: list[Path] = []

    async def send_text(self, text: str, button: Any = None) -> None:
        self.texts.append(text)

    async def send_voice(self, path: Path) -> None:
        self.voices.append(path)


async def _row(session: Any, audio: Path | str) -> Any:
    from techradar.db.models import VoiceSession

    row = VoiceSession(source="telegram", duration_s=5.0, status="queued", audio_path=str(audio))
    session.add(row)
    await session.flush()
    return row


# --- deletion stays inside the voice folder ---------------------------------------------------


def test_unlink_removes_a_hash_named_note_in_the_voice_folder(tmp_path: Path) -> None:
    voice_dir = _voice_dir(tmp_path)
    _unlink_file(str(voice_dir / "in" / NAME), voice_dir)
    assert not (voice_dir / "in" / NAME).exists()


@pytest.mark.parametrize("where", ["outside", "dotdot", "not_hash", "other_ext"])
def test_unlink_never_removes_a_file_outside_the_voice_folder(tmp_path: Path, where: str) -> None:
    voice_dir = _voice_dir(tmp_path)
    precious = tmp_path / "precious.ogg"
    precious.write_bytes(b"keep")
    pdf = voice_dir / "in" / (hashlib.sha256(b"pdf").hexdigest() + ".pdf")
    pdf.write_bytes(b"pdf")
    path = {
        "outside": str(precious),
        "dotdot": str(voice_dir / "in" / ".." / ".." / "precious.ogg"),
        "not_hash": str(voice_dir / "in" / "precious.ogg"),
        "other_ext": str(pdf),  # voice notes only: never another hash-named file
    }[where]
    (voice_dir / "in" / "precious.ogg").write_bytes(b"keep")
    _unlink_file(path, voice_dir)
    assert precious.read_bytes() == b"keep"
    assert (voice_dir / "in" / "precious.ogg").exists()
    assert pdf.exists()


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


def test_unlink_reply_through_a_symlinked_out_folder_does_nothing(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    (real / "reply_5.ogg").write_bytes(b"x")
    (tmp_path / "voice").mkdir()
    (tmp_path / "voice" / "out").symlink_to(real)
    _unlink_reply(tmp_path / "voice", 5)
    assert (real / "reply_5.ogg").exists()


# --- the analysis job: checked before decoding, a deletion time on every path ----------------


@pytest.mark.db
async def test_analysis_refuses_a_file_that_is_not_a_voice_note(
    session: Any, tmp_path: Path
) -> None:
    voice_dir = tmp_path / "voice"
    (voice_dir / "in").mkdir(parents=True)
    data = b"MZ\x90\x00 an exe renamed"
    f = voice_dir / "in" / (hashlib.sha256(data).hexdigest() + ".ogg")
    f.write_bytes(data)
    row = await _row(session, f)
    transcriber = MagicMock()
    outbox = FakeOutbox()
    with unittest.mock.patch("techradar.voice.jobs.decode_audio") as decode:
        await analyse_voice(
            session,
            row.id,
            transcriber=transcriber,
            phoneme_model=MagicMock(),
            completer=MagicMock(),
            outbox=outbox,
            voice_dir=voice_dir,
            now=NOW,
            probe=lambda _p: "not ogg",
        )
    assert row.status == "failed"
    assert row.delete_after == NOW + timedelta(hours=24)  # refused notes are deleted too
    assert outbox.texts == ["I can only analyse Telegram voice notes."]
    decode.assert_not_called()
    transcriber.transcribe.assert_not_called()  # nothing decoded or transcribed


@pytest.mark.db
async def test_a_probe_that_crashes_refuses_the_note(session: Any, tmp_path: Path) -> None:
    voice_dir = _voice_dir(tmp_path)
    row = await _row(session, voice_dir / "in" / NAME)
    outbox = FakeOutbox()

    def crash(_p: Path) -> str | None:
        raise OSError("too many levels of symbolic links")

    with unittest.mock.patch("techradar.voice.jobs.decode_audio") as decode:
        await analyse_voice(
            session,
            row.id,
            transcriber=FakeTranscriber(),
            phoneme_model=FakePhonemeModel(),
            completer=FakeCompleter([]),
            outbox=outbox,
            voice_dir=voice_dir,
            now=NOW,
            probe=crash,
        )
    decode.assert_not_called()
    assert row.status == "failed" and row.delete_after == NOW + timedelta(hours=24)
    assert outbox.texts == ["I can only analyse Telegram voice notes."]


@pytest.mark.db
async def test_silent_note_still_gets_a_deletion_time(session: Any, tmp_path: Path) -> None:
    voice_dir = _voice_dir(tmp_path)
    audio = voice_dir / "in" / NAME
    row = await _row(session, audio)
    silent = Transcript(text="", words=[], lang="en", duration_s=5.0)
    with unittest.mock.patch(
        "techradar.voice.jobs.decode_audio", return_value=np.zeros(16000, dtype=np.float32)
    ):
        await analyse_voice(
            session,
            row.id,
            transcriber=FakeTranscriber(silent),
            phoneme_model=FakePhonemeModel(),
            completer=FakeCompleter([]),
            outbox=FakeOutbox(),
            voice_dir=voice_dir,
            now=NOW,
            probe=lambda _p: None,  # the test bytes are not a real Ogg file
        )
    assert row.status == "no_speech" and row.delete_after == NOW + timedelta(hours=24)
    assert await cleanup_voice(session, now=NOW + timedelta(hours=25), voice_dir=voice_dir) == 1
    assert not audio.exists()


@pytest.mark.db
async def test_a_crashing_engine_fails_the_note_and_keeps_the_deletion_time(
    session: Any, tmp_path: Path
) -> None:
    voice_dir = _voice_dir(tmp_path)
    row = await _row(session, voice_dir / "in" / NAME)
    outbox = FakeOutbox()
    with unittest.mock.patch("techradar.voice.jobs.decode_audio", side_effect=RuntimeError("boom")):
        await analyse_voice(
            session,
            row.id,
            transcriber=FakeTranscriber(),
            phoneme_model=FakePhonemeModel(),
            completer=FakeCompleter([]),
            outbox=outbox,
            voice_dir=voice_dir,
            now=NOW,
            probe=lambda _p: None,
        )
    assert outbox.texts == ["I couldn't analyse that note. Please try again."]
    assert row.status == "failed" and row.delete_after is not None


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
async def test_unavailable_analysis_sets_a_missing_deletion_time(
    session: Any, tmp_path: Path
) -> None:
    row = await _row(session, _voice_dir(tmp_path) / "in" / NAME)
    assert row.delete_after is None
    assert await mark_voice_unavailable(session, row.id, now=NOW) is True
    assert row.status == "failed" and row.delete_after == NOW + timedelta(hours=24)


@pytest.mark.db
async def test_unavailable_analysis_never_pushes_the_deletion_time_out(
    session: Any, tmp_path: Path
) -> None:
    row = await _row(session, _voice_dir(tmp_path) / "in" / NAME)
    row.delete_after = NOW + timedelta(hours=2)
    assert await mark_voice_unavailable(session, row.id, now=NOW) is True
    assert row.delete_after == NOW + timedelta(hours=2)


# --- Keep and the hourly cleanup ---------------------------------------------------------------


@pytest.mark.db
async def test_keep_stops_deletion_and_cleanup_removes_our_reply(
    session: Any, tmp_path: Path
) -> None:
    voice_dir = tmp_path / "voice"
    kept_audio, gone_audio = _note(voice_dir, "k"), _note(voice_dir, "g")
    kept, gone = await _row(session, kept_audio), await _row(session, gone_audio)
    for r in (kept, gone):
        r.delete_after = NOW
    out = voice_dir / "out"
    out.mkdir()
    reply = out / f"reply_{gone.id}.ogg"
    reply.write_bytes(b"x")

    assert await keep_voice(session, kept.id) is True
    assert await keep_voice(session, 999_999) is False
    assert await cleanup_voice(session, now=NOW + timedelta(hours=1), voice_dir=voice_dir) == 1
    assert kept_audio.exists() and not gone_audio.exists() and not reply.exists()


@pytest.mark.db
async def test_cleanup_deletes_expired_notes_and_replies_unless_kept(
    session: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from techradar.db.models import VoiceSession

    monkeypatch.setattr(session, "commit", session.flush)  # the fixture rolls back
    voice_dir = tmp_path / "voice"
    (voice_dir / "out").mkdir(parents=True)
    notes = {tag: _note(voice_dir, tag) for tag in ("expired", "kept", "fresh")}
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


def test_cleanup_needs_the_voice_folder() -> None:
    import inspect

    # No default: a caller can never fall back to deleting whatever path the database holds.
    param = inspect.signature(cleanup_voice).parameters["voice_dir"]
    assert param.default is inspect.Parameter.empty
