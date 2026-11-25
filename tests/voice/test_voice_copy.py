"""The analysis opens the stored voice note once and decodes only a private copy (SEC-57).

The file that `probe` checks is the file that is decoded and transcribed: swapping, linking or
editing the note in voice/in after intake, or after the check, changes nothing.

SEC: SEC-15, SEC-57.
"""

from __future__ import annotations

import hashlib
import os
import stat
import unittest.mock
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from techradar.intake.owner_files import UnsafeFile
from techradar.voice.intake import private_voice_copy, remove_voice_copy
from techradar.voice.jobs import NO_SPEECH_TEXT, analyse_voice
from techradar.voice.transcribe import Transcript
from tests.fakes import FakeCompleter, FakePhonemeModel, FakeTranscriber

NOW = datetime(2026, 11, 25, 6, 0, tzinfo=UTC)
OGG = b"OggS\x00\x02" + b"v" * 100
NAME = hashlib.sha256(OGG).hexdigest() + ".ogg"
SILENT = Transcript(text="", words=[], lang="en", duration_s=5.0)


def _voice_dir(tmp_path: Path) -> Path:
    voice_dir = tmp_path / "voice"
    (voice_dir / "in").mkdir(parents=True)
    (voice_dir / "in" / NAME).write_bytes(OGG)
    return voice_dir


# --- private_voice_copy ------------------------------------------------------------------------


def test_copy_is_private_and_holds_the_stored_bytes(tmp_path: Path) -> None:
    voice_dir = _voice_dir(tmp_path)
    copy = private_voice_copy(voice_dir, str(voice_dir / "in" / NAME), work_root=tmp_path)
    try:
        assert copy.read_bytes() == OGG
        assert stat.S_IMODE(os.lstat(copy).st_mode) == 0o600
        assert stat.S_IMODE(os.lstat(copy.parent).st_mode) == 0o700
        assert copy.parent != voice_dir / "in"
    finally:
        remove_voice_copy(copy)
    assert not copy.parent.exists()
    assert (voice_dir / "in" / NAME).read_bytes() == OGG  # the stored note is untouched


def test_copy_refuses_a_hard_linked_note(tmp_path: Path) -> None:
    voice_dir = _voice_dir(tmp_path)
    os.link(voice_dir / "in" / NAME, tmp_path / "elsewhere.ogg")
    with pytest.raises(UnsafeFile, match="other links"):
        private_voice_copy(voice_dir, str(voice_dir / "in" / NAME), work_root=tmp_path)


def test_copy_refuses_bytes_that_do_not_match_the_name(tmp_path: Path) -> None:
    voice_dir = _voice_dir(tmp_path)
    (voice_dir / "in" / NAME).write_bytes(OGG + b"edited after intake")
    with pytest.raises(UnsafeFile, match="does not match"):
        private_voice_copy(voice_dir, str(voice_dir / "in" / NAME), work_root=tmp_path)


@pytest.mark.parametrize("where", ["outside", "dotdot", "nested", "not_hash", "other_ext"])
def test_copy_refuses_a_path_whose_parent_is_not_voice_in(tmp_path: Path, where: str) -> None:
    voice_dir = _voice_dir(tmp_path)
    (tmp_path / NAME).write_bytes(OGG)
    (voice_dir / "in" / "sub").mkdir()
    (voice_dir / "in" / "sub" / NAME).write_bytes(OGG)
    pdf = hashlib.sha256(OGG).hexdigest() + ".pdf"
    (voice_dir / "in" / pdf).write_bytes(OGG)
    path = {
        "outside": tmp_path / NAME,
        "dotdot": voice_dir / "in" / ".." / "in" / NAME,
        "nested": voice_dir / "in" / "sub" / NAME,
        "not_hash": voice_dir / "in" / "note.ogg",
        "other_ext": voice_dir / "in" / pdf,
    }[where]
    with pytest.raises(UnsafeFile, match="not a stored voice note"):
        private_voice_copy(voice_dir, str(path), work_root=tmp_path)


def test_copy_refuses_a_planted_symlink_and_a_symlinked_folder(tmp_path: Path) -> None:
    voice_dir = tmp_path / "voice"
    (voice_dir / "in").mkdir(parents=True)
    target = tmp_path / "target.ogg"
    target.write_bytes(OGG)
    (voice_dir / "in" / NAME).symlink_to(target)
    with pytest.raises(UnsafeFile):
        private_voice_copy(voice_dir, str(voice_dir / "in" / NAME), work_root=tmp_path)

    other = tmp_path / "other"
    other.mkdir()
    real = tmp_path / "real"
    real.mkdir()
    (real / NAME).write_bytes(OGG)
    (other / "in").symlink_to(real)
    with pytest.raises(UnsafeFile):
        private_voice_copy(other, str(other / "in" / NAME), work_root=tmp_path)


def test_copy_refuses_a_note_over_the_limit(tmp_path: Path) -> None:
    voice_dir = _voice_dir(tmp_path)
    with pytest.raises(UnsafeFile, match="too large"):
        private_voice_copy(
            voice_dir, str(voice_dir / "in" / NAME), max_bytes=len(OGG) - 1, work_root=tmp_path
        )


def test_remove_voice_copy_only_removes_a_copy_folder(tmp_path: Path) -> None:
    keep = tmp_path / "keep"
    keep.mkdir()
    (keep / "note.ogg").write_bytes(b"x")
    remove_voice_copy(keep / "note.ogg")
    assert (keep / "note.ogg").exists()


# --- analyse_voice reads the copy only ----------------------------------------------------------


class FakeSession:
    """Just enough of AsyncSession for analyse_voice's no-speech and refusal paths."""

    def __init__(self, row: Any) -> None:
        self.row = row
        self.commits = 0

    async def execute(self, _stmt: Any) -> Any:
        return SimpleNamespace(scalar_one_or_none=lambda: self.row)

    async def get(self, _model: Any, _id: int) -> Any:
        return self.row

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        pass

    def add(self, _obj: Any) -> None:
        pass


class FakeOutbox:
    def __init__(self) -> None:
        self.texts: list[str] = []

    async def send_text(self, text: str, button: Any = None) -> None:
        self.texts.append(text)

    async def send_voice(self, path: Path) -> None:
        pass


def _row(path: Path | str) -> SimpleNamespace:
    return SimpleNamespace(
        id=1,
        audio_path=str(path),
        status="queued",
        delete_after=None,
        duration_s=5.0,
        peaks=None,
        transcript=None,
    )


async def _run(session: FakeSession, voice_dir: Path, probe: Any, **kw: Any) -> FakeOutbox:
    outbox = FakeOutbox()
    await analyse_voice(
        session,  # type: ignore[arg-type]
        1,
        transcriber=kw.pop("transcriber", FakeTranscriber(SILENT)),
        phoneme_model=FakePhonemeModel(),
        completer=FakeCompleter([]),
        outbox=outbox,
        voice_dir=voice_dir,
        now=NOW,
        probe=probe,
    )
    return outbox


async def test_a_swap_after_the_probe_changes_nothing_that_is_decoded(tmp_path: Path) -> None:
    voice_dir = _voice_dir(tmp_path)
    stored = voice_dir / "in" / NAME
    evil = tmp_path / "evil.bin"
    evil.write_bytes(b"MZ not a voice note")
    probed: list[Path] = []
    decoded: list[tuple[Path, bytes]] = []

    def probe(p: Path) -> str | None:
        probed.append(p)
        assert p.read_bytes() == OGG
        # The attacker swaps the stored note for a link to another file right after the check.
        stored.unlink()
        stored.symlink_to(evil)
        return None

    def decode(p: Path) -> Any:
        decoded.append((p, p.read_bytes()))
        return np.zeros(16000, dtype=np.float32)

    transcriber = FakeTranscriber(SILENT)
    session = FakeSession(_row(stored))
    with unittest.mock.patch("techradar.voice.jobs.decode_audio", side_effect=decode):
        outbox = await _run(session, voice_dir, probe, transcriber=transcriber)

    assert len(probed) == 1 and probed[0] != stored
    assert decoded == [(probed[0], OGG)]  # the checked copy, with the checked bytes
    assert transcriber.calls == [probed[0]]
    assert not probed[0].exists() and not probed[0].parent.exists()  # the copy is gone
    assert session.row.status == "no_speech" and outbox.texts == [NO_SPEECH_TEXT]
    assert session.row.delete_after == NOW + timedelta(hours=24)


@pytest.mark.parametrize("attack", ["hard_link", "hash_mismatch", "outside", "symlink"])
async def test_an_unsafe_stored_note_is_never_probed_or_decoded(
    tmp_path: Path, attack: str
) -> None:
    voice_dir = _voice_dir(tmp_path)
    stored = voice_dir / "in" / NAME
    path: Path = stored
    if attack == "hard_link":
        os.link(stored, tmp_path / "elsewhere.ogg")
    elif attack == "hash_mismatch":
        stored.write_bytes(OGG + b"changed")
    elif attack == "outside":
        path = tmp_path / NAME
        path.write_bytes(OGG)
    else:
        stored.unlink()
        (tmp_path / "t.ogg").write_bytes(OGG)
        stored.symlink_to(tmp_path / "t.ogg")

    probed: list[Path] = []
    transcriber = FakeTranscriber(SILENT)
    session = FakeSession(_row(path))
    with unittest.mock.patch("techradar.voice.jobs.decode_audio") as decode:
        outbox = await _run(session, voice_dir, lambda p: probed.append(p), transcriber=transcriber)

    assert probed == [] and transcriber.calls == []
    decode.assert_not_called()
    assert session.row.status == "failed"
    assert session.row.delete_after == NOW + timedelta(hours=24)
    assert outbox.texts == ["I can only analyse Telegram voice notes."]


async def test_a_missing_note_fails_with_a_deletion_time(tmp_path: Path) -> None:
    voice_dir = _voice_dir(tmp_path)
    (voice_dir / "in" / NAME).unlink()
    session = FakeSession(_row(voice_dir / "in" / NAME))
    with unittest.mock.patch("techradar.voice.jobs.decode_audio") as decode:
        outbox = await _run(session, voice_dir, lambda _p: None)
    decode.assert_not_called()
    assert session.row.status == "failed"
    assert session.row.delete_after == NOW + timedelta(hours=24)
    assert outbox.texts == ["I couldn't analyse that note. Please try again."]


async def test_the_copy_is_removed_when_the_probe_refuses_or_decoding_crashes(
    tmp_path: Path,
) -> None:
    voice_dir = _voice_dir(tmp_path)
    seen: list[Path] = []

    def refuse(p: Path) -> str | None:
        seen.append(p)
        return "not ogg"

    session = FakeSession(_row(voice_dir / "in" / NAME))
    outbox = await _run(session, voice_dir, refuse)
    assert outbox.texts == ["I can only analyse Telegram voice notes."]
    assert seen and not seen[0].parent.exists()

    seen.clear()

    def accept(p: Path) -> str | None:
        seen.append(p)
        return None

    session = FakeSession(_row(voice_dir / "in" / NAME))
    with unittest.mock.patch("techradar.voice.jobs.decode_audio", side_effect=RuntimeError("x")):
        outbox = await _run(session, voice_dir, accept)
    assert outbox.texts == ["I couldn't analyse that note. Please try again."]
    assert session.row.status == "failed" and session.row.delete_after is not None
    assert seen and not seen[0].parent.exists()
