from __future__ import annotations

import numpy as np
import pytest

from techradar.voice.pronounce import score_words
from techradar.voice.transcribe import Word
from tests.fakes import FakePhonemeModel


def test_score_words_flags_low_scores() -> None:
    ws = score_words(
        np.zeros(32_000, dtype=np.float32),
        [Word(text="world", start=0.2, end=0.8, prob=1.0)],
        FakePhonemeModel(prob=0.3),
    )
    assert ws[0].flagged
    assert ws[0].score == pytest.approx(0.3, abs=0.05)


def test_short_words_are_skipped() -> None:
    ws = score_words(
        np.zeros(32_000, dtype=np.float32),
        [Word(text="is", start=0.1, end=0.3, prob=1.0)],
        FakePhonemeModel(prob=0.1),
    )
    assert not ws[0].flagged
    assert ws[0].score == 1.0
