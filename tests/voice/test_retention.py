"""Audio retention and the failure paths of the analysis job (Phase 6 Task 6)."""

from __future__ import annotations

import unittest.mock
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from techradar.db.models import VoiceSession
from techradar.voice.jobs import analyse_voice, cleanup_voice, keep_voice, mark_not_set_up
from techradar.voice.transcribe import Transcript
from tests.fakes import FakeCompleter, FakePhonemeModel, FakeTranscriber

NOW = datetime(2026, 11, 25, 12, 0, tzinfo=UTC)


class FakeOutbox:
    def __init__(self) -> None:
        self.texts: list[str] = []
        self.voices: list[Path] = []

    async def send_text(self, text: str, button: Any = None) -> None:
        self.texts.append(text)

    async def send_voice(self, path: Path) -> None:
        self.voices.append(path)


async def _row(session: Any, audio: Path) -> VoiceSession:
    row = VoiceSession(source="telegram", duration_s=5.0, status="queued", audio_path=str(audio))
    session.add(row)
    await session.flush()
    return row


@pytest.mark.db
async def test_silent_note_still_gets_a_deletion_time(session: Any, tmp_path: Path) -> None:
    audio = tmp_path / "a.ogg"
    audio.write_bytes(b"x")
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
            now=NOW,
        )
    assert row.status == "no_speech" and row.delete_after == NOW + timedelta(hours=24)
    assert await cleanup_voice(session, now=NOW + timedelta(hours=25)) == 1
    assert not audio.exists()


@pytest.mark.db
async def test_a_crashing_engine_fails_the_note_and_keeps_the_deletion_time(
    session: Any, tmp_path: Path
) -> None:
    audio = tmp_path / "a.ogg"
    audio.write_bytes(b"x")
    row = await _row(session, audio)
    outbox = FakeOutbox()
    with unittest.mock.patch("techradar.voice.jobs.decode_audio", side_effect=RuntimeError("boom")):
        await analyse_voice(
            session,
            row.id,
            transcriber=FakeTranscriber(),
            phoneme_model=FakePhonemeModel(),
            completer=FakeCompleter([]),
            outbox=outbox,
            now=NOW,
        )
    assert outbox.texts == ["I couldn't analyse that note. Please try again."]
    assert row.status == "failed" and row.delete_after is not None


@pytest.mark.db
async def test_keep_stops_deletion_and_cleanup_removes_our_reply(
    session: Any, tmp_path: Path
) -> None:
    kept_audio, gone_audio = tmp_path / "k.ogg", tmp_path / "g.ogg"
    kept_audio.write_bytes(b"x")
    gone_audio.write_bytes(b"x")
    kept, gone = await _row(session, kept_audio), await _row(session, gone_audio)
    for r in (kept, gone):
        r.delete_after = NOW
    out = tmp_path / "out"
    out.mkdir()
    reply = out / f"reply_{gone.id}.ogg"
    reply.write_bytes(b"x")

    assert await keep_voice(session, kept.id) is True
    assert await keep_voice(session, 999_999) is False
    assert await cleanup_voice(session, now=NOW + timedelta(hours=1), voice_dir=tmp_path) == 1
    assert kept_audio.exists() and not gone_audio.exists() and not reply.exists()


@pytest.mark.db
async def test_not_set_up_fails_the_note_and_says_so(session: Any, tmp_path: Path) -> None:
    audio = tmp_path / "a.ogg"
    audio.write_bytes(b"x")
    row = await _row(session, audio)
    outbox = FakeOutbox()
    await mark_not_set_up(session, row.id, outbox, "not set up", now=NOW)
    assert outbox.texts == ["not set up"] and row.status == "failed"
    assert row.delete_after == NOW + timedelta(hours=24)
