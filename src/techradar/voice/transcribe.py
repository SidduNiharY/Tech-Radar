from __future__ import annotations

from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict

FILLER_PROMPT: str = "Umm, let me think like, hmm... Okay, here's what I'm, like, thinking."


class Word(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    start: float
    end: float
    prob: float


class Transcript(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    words: list[Word]
    lang: str
    duration_s: float


class Transcriber(Protocol):
    def transcribe(self, path: Path) -> Transcript: ...


def no_speech(t: Transcript) -> bool:
    """True if fewer than 3 words or the duration is under 1 s."""
    return len(t.words) < 3 or t.duration_s < 1.0
