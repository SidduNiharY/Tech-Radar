from __future__ import annotations

from pathlib import Path

from techradar.voice.transcribe import (
    FILLER_PROMPT,
    Transcript,
    Word,
    no_speech,
)
from tests.fakes import FakeTranscriber


def test_silence_gives_no_speech():
    assert no_speech(Transcript(text="", words=[], lang="en", duration_s=5.0))
    # Under 1 second
    assert no_speech(
        Transcript(
            text="hi there",
            words=[
                Word(text="hi", start=0.1, end=0.4, prob=0.9),
                Word(text="there", start=0.4, end=0.8, prob=0.9),
            ],
            lang="en",
            duration_s=0.9,
        )
    )


def test_valid_transcript_has_speech():
    t = Transcript(
        text="hello there world",
        words=[
            Word(text="hello", start=0.0, end=0.5, prob=0.95),
            Word(text="there", start=0.5, end=1.0, prob=0.90),
            Word(text="world", start=1.0, end=1.5, prob=0.92),
        ],
        lang="en",
        duration_s=2.5,
    )
    assert not no_speech(t)


def test_fake_transcriber(tmp_path: Path):
    t = Transcript(
        text="test speech",
        words=[Word(text="test", start=0, end=0.5, prob=1.0)],
        lang="en",
        duration_s=1.5,
    )
    fake = FakeTranscriber(t)
    res = fake.transcribe(tmp_path / "voice.ogg")
    assert res.text == "test speech"
    assert len(fake.calls) == 1
    assert "Umm" in FILLER_PROMPT
