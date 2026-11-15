from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from typing import Any, Protocol

import numpy as np
from pydantic import BaseModel, ConfigDict

from techradar.voice.align import ctc_force_align, phone_scores, to_vocab_ids
from techradar.voice.transcribe import Word

_logger = logging.getLogger(__name__)

FRAME_S: float = 0.02
FLAG_THRESHOLD: float = 0.5


def expected_ipa(word: str, voice: str = "en-gb") -> str:
    """Derive expected International Phonetic Alphabet symbols for a word."""
    cleaned = "".join(c for c in word.lower() if c.isalpha())
    try:
        from phonemizer import phonemize

        res = phonemize(
            cleaned,
            language=voice,
            backend="espeak",
            strip=True,
            with_stress=False,
        )
        if isinstance(res, str):
            return res.strip()
    except Exception as exc:
        _logger.debug("phonemizer fallback for word '%s': %s", cleaned, exc)
    # Fallback deterministic pseudo-phonemes for environments without espeak
    return cleaned


class PhonemeModel(Protocol):
    vocab: Mapping[str, int]
    blank_id: int

    def log_probs(self, wav: Any) -> Any: ...


class WordScore(BaseModel):
    model_config = ConfigDict(frozen=True)

    word: str
    start_s: float
    end_s: float
    score: float
    flagged: bool


def score_words(
    wav: Any,
    words: Sequence[Word],
    model: PhonemeModel,
) -> list[WordScore]:
    """Score word pronunciation quality using CTC forced alignment on phoneme outputs."""
    scores: list[WordScore] = []
    sr = 16_000

    for w in words:
        clean_w = "".join(c for c in w.text.lower() if c.isalpha())
        if len(clean_w) <= 2:
            scores.append(
                WordScore(
                    word=w.text,
                    start_s=w.start,
                    end_s=w.end,
                    score=1.0,
                    flagged=False,
                )
            )
            continue

        ipa = expected_ipa(clean_w)
        target_ids = to_vocab_ids(ipa, model.vocab)
        if not target_ids:
            scores.append(
                WordScore(
                    word=w.text,
                    start_s=w.start,
                    end_s=w.end,
                    score=1.0,
                    flagged=False,
                )
            )
            continue

        # Slice wav with 0.1s padding
        pad_s = 0.1
        t_start = max(0.0, w.start - pad_s)
        t_end = min(len(wav) / sr, w.end + pad_s)
        idx_start = int(t_start * sr)
        idx_end = max(idx_start + 1, int(t_end * sr))

        segment = wav[idx_start:idx_end]
        lp = model.log_probs(segment)

        try:
            alignment = ctc_force_align(lp, target_ids, blank=model.blank_id)
            p_scores = phone_scores(lp, alignment, target_ids)
            word_score = float(np.mean(p_scores)) if p_scores else 1.0
        except Exception:
            word_score = 1.0

        rounded_score = round(word_score, 3)
        flagged = rounded_score < FLAG_THRESHOLD

        scores.append(
            WordScore(
                word=w.text,
                start_s=w.start,
                end_s=w.end,
                score=rounded_score,
                flagged=flagged,
            )
        )

    return scores
