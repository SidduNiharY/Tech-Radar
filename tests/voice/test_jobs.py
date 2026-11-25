from __future__ import annotations

import hashlib
import unittest.mock
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from techradar.db.models import VoiceSession
from techradar.voice.jobs import analyse_voice, cleanup_voice
from techradar.voice.transcribe import Transcript, Word
from tests.fakes import FakeCompleter, FakePhonemeModel, FakeTranscriber


def _stored(tmp_path: Path, data: bytes) -> tuple[Path, Path]:
    """(voice_dir, note): a hash-named note in voice_dir/in, as intake stores it."""
    voice_dir = tmp_path / "voice"
    (voice_dir / "in").mkdir(parents=True, exist_ok=True)
    note = voice_dir / "in" / (hashlib.sha256(data).hexdigest() + ".ogg")
    note.write_bytes(data)
    return voice_dir, note


class FakeOutbox:
    def __init__(self) -> None:
        self.texts: list[str] = []
        self.buttons: list[Any] = []

    async def send_text(self, text: str, button: Any = None) -> None:
        self.texts.append(text)
        self.buttons.append(button)


@pytest.mark.db
async def test_no_speech_reply(session: Any, tmp_path: Path) -> None:
    voice_dir, audio_file = _stored(tmp_path, b"dummy")

    voice_row = VoiceSession(
        source="telegram",
        duration_s=5.0,
        status="queued",
        audio_path=str(audio_file),
    )
    session.add(voice_row)
    await session.flush()

    outbox = FakeOutbox()
    silent_transcript = Transcript(text="", words=[], lang="en", duration_s=5.0)

    with unittest.mock.patch(
        "techradar.voice.jobs.decode_audio",
        return_value=np.zeros(16000, dtype=np.float32),
    ):
        await analyse_voice(
            session,
            voice_row.id,
            transcriber=FakeTranscriber(silent_transcript),
            phoneme_model=FakePhonemeModel(),
            completer=FakeCompleter([]),
            outbox=outbox,
            voice_dir=voice_dir,
            probe=lambda _p: None,  # the dummy bytes are not a real Ogg file
        )

    assert outbox.texts == ["I couldn't hear speech in that note."]
    assert voice_row.status == "no_speech"


@pytest.mark.db
async def test_audio_deleted_after_24h_unless_kept(session: Any, tmp_path: Path) -> None:
    voice_dir, audio_file = _stored(tmp_path, b"content")

    t = Transcript(
        text="hello world this is a test note",
        words=[
            Word(text="hello", start=0, end=0.5, prob=1.0),
            Word(text="world", start=0.5, end=1.0, prob=1.0),
            Word(text="test", start=1.0, end=1.5, prob=1.0),
        ],
        lang="en",
        duration_s=3.0,
    )

    voice_row = VoiceSession(
        source="telegram",
        duration_s=3.0,
        status="queued",
        audio_path=str(audio_file),
    )
    session.add(voice_row)
    await session.flush()

    with unittest.mock.patch(
        "techradar.voice.jobs.decode_audio",
        return_value=np.zeros(16000, dtype=np.float32),
    ):
        await analyse_voice(
            session,
            voice_row.id,
            transcriber=FakeTranscriber(t),
            phoneme_model=FakePhonemeModel(),
            completer=FakeCompleter([]),
            outbox=FakeOutbox(),
            voice_dir=voice_dir,
            probe=lambda _p: None,  # the dummy bytes are not a real Ogg file
        )

    assert audio_file.exists()
    assert voice_row.delete_after is not None

    # Run cleanup past 24h
    now = datetime.now(UTC) + timedelta(hours=25)
    cleaned = await cleanup_voice(session, now=now, voice_dir=voice_dir)

    assert cleaned == 1
    assert not audio_file.exists()
    assert voice_row.audio_path is None
