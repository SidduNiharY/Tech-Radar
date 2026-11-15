from __future__ import annotations

import pytest

from techradar.voice.metrics import compute_metrics
from techradar.voice.transcribe import Transcript, Word


def transcript_from(text: str, duration_s: float = 60.0) -> Transcript:
    words_list: list[Word] = []
    tokens = text.split()
    step = duration_s / max(len(tokens), 1)
    for i, tok in enumerate(tokens):
        words_list.append(
            Word(
                text=tok,
                start=round(i * step, 2),
                end=round((i + 1) * step - 0.05, 2),
                prob=1.0,
            )
        )
    return Transcript(
        text=text,
        words=words_list,
        lang="en",
        duration_s=duration_s,
    )


def transcript_with_timings(timings: list[tuple[str, float, float]]) -> Transcript:
    words_list = [Word(text=w, start=s, end=e, prob=1.0) for w, s, e in timings]
    text = " ".join(w for w, _, _ in timings)
    duration = timings[-1][2] if timings else 0.0
    return Transcript(
        text=text,
        words=words_list,
        lang="en",
        duration_s=duration,
    )


def test_filler_counts_and_rate():
    m = compute_metrics(transcript_from("um so I think uh the rate um stayed", duration_s=60.0))
    assert m.filler_breakdown == {"um": 2, "uh": 1}
    assert m.filler_count == 3
    assert m.fillers_per_min == 3.0


def test_like_only_counted_as_filler_before_pause():
    # Gap between 'like' (0.4) and 'it' (0.5) is 0.1 (< 0.3) -> not filler
    t1 = transcript_with_timings([("I", 0.0, 0.2), ("like", 0.2, 0.4), ("it", 0.5, 0.6)])
    assert compute_metrics(t1).filler_count == 0

    # Gap between 'like' (0.2) and 'the' (0.6) is 0.4 (>= 0.3) -> filler
    t2 = transcript_with_timings([("like", 0.0, 0.2), ("the", 0.6, 0.7)])
    assert compute_metrics(t2).filler_count == 1


def test_long_pauses_and_ttr():
    # Gap between 'a' (0.2) and 'b' (1.5) is 1.3 (> 1.0) -> 1 long pause
    # Tokens: a, b, a -> unique: 2, total: 3 -> TTR = 0.67
    t = transcript_with_timings([("a", 0.0, 0.2), ("b", 1.5, 1.7), ("a", 1.8, 2.0)])
    m = compute_metrics(t)
    assert m.long_pauses == 1
    assert m.type_token_ratio == pytest.approx(0.67, abs=0.01)


def test_overused_words():
    # "paradigm" repeated 6 times (non-stopword)
    # "the" repeated 10 times (stopword, ignored)
    tokens = ["the"] * 10 + ["paradigm"] * 6
    text = " ".join(tokens)
    t = transcript_from(text, duration_s=30.0)
    m = compute_metrics(t)
    assert m.overused == [("paradigm", 6)]
