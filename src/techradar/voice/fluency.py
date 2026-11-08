from __future__ import annotations

import re
from typing import Final

from pydantic import BaseModel, Field

FILLER_WORDS: Final[frozenset[str]] = frozenset(
    ["um", "uh", "er", "ah", "like", "you know", "actually", "basically", "literally"]
)


class FluencyMetrics(BaseModel):
    """Speech fluency analysis metrics."""

    word_count: int = Field(ge=0, description="Total word count of the transcript")
    duration_seconds: float = Field(ge=0.0, description="Duration of speech in seconds")
    words_per_minute: float = Field(ge=0.0, description="Speaking rate in words per minute")
    filler_word_count: int = Field(ge=0, description="Total count of filler words or phrases")
    filler_word_frequency_pct: float = Field(
        ge=0.0, description="Filler word count divided by word count * 100"
    )
    filler_words_breakdown: dict[str, int] = Field(
        default_factory=dict, description="Count breakdown by filler word or phrase"
    )
    fluency_score: float = Field(ge=0.0, le=100.0, description="Fluency score from 0.0 to 100.0")


def _tokenize_words(text: str) -> list[str]:
    """Tokenize transcript into lowercase word tokens."""
    return re.findall(r"\b[a-zA-Z0-9]+(?:'[a-zA-Z0-9]+)?\b", text.lower())


def analyze_fluency(
    transcript: str,
    duration_seconds: float,
    filler_words: frozenset[str] | set[str] = FILLER_WORDS,
) -> FluencyMetrics:
    """Analyze speech fluency from a transcript and speaking duration in seconds."""
    effective_duration = max(0.0, float(duration_seconds))
    words = _tokenize_words(transcript)
    word_count = len(words)

    if effective_duration == 0.0 or word_count == 0:
        return FluencyMetrics(
            word_count=word_count,
            duration_seconds=effective_duration,
            words_per_minute=0.0,
            filler_word_count=0,
            filler_word_frequency_pct=0.0,
            filler_words_breakdown={},
            fluency_score=0.0,
        )

    # Separate multi-word phrases from single-word fillers
    multi_word_fillers: list[tuple[list[str], str]] = []
    single_word_fillers: set[str] = set()

    for item in filler_words:
        cleaned = item.strip().lower()
        parts = cleaned.split()
        if len(parts) > 1:
            multi_word_fillers.append((parts, cleaned))
        elif parts:
            single_word_fillers.add(cleaned)

    # Sort multi-word phrases descending by word count to greedily match longest phrases first
    multi_word_fillers.sort(key=lambda x: len(x[0]), reverse=True)

    breakdown: dict[str, int] = {}
    i = 0
    total_tokens = len(words)

    while i < total_tokens:
        matched = False
        for phrase_tokens, phrase_str in multi_word_fillers:
            phrase_len = len(phrase_tokens)
            if i + phrase_len <= total_tokens and words[i : i + phrase_len] == phrase_tokens:
                breakdown[phrase_str] = breakdown.get(phrase_str, 0) + 1
                i += phrase_len
                matched = True
                break

        if matched:
            continue

        token = words[i]
        if token in single_word_fillers:
            breakdown[token] = breakdown.get(token, 0) + 1

        i += 1

    filler_count = sum(breakdown.values())
    filler_freq_pct = round((filler_count / word_count) * 100.0, 2)
    wpm = round((word_count / effective_duration) * 60.0, 2)

    # Fluency Score Calibration (0.0 to 100.0)
    # Target speaking rate is 100 to 200 WPM; penalize extreme speaking rate
    wpm_penalty = 0.0
    if wpm < 100.0:
        wpm_penalty = (100.0 - wpm) * 0.5
    elif wpm > 200.0:
        wpm_penalty = (wpm - 200.0) * 0.5

    filler_penalty = filler_freq_pct * 2.5
    raw_score = 100.0 - wpm_penalty - filler_penalty
    fluency_score = round(max(0.0, min(100.0, raw_score)), 2)

    return FluencyMetrics(
        word_count=word_count,
        duration_seconds=effective_duration,
        words_per_minute=wpm,
        filler_word_count=filler_count,
        filler_word_frequency_pct=filler_freq_pct,
        filler_words_breakdown=breakdown,
        fluency_score=fluency_score,
    )
