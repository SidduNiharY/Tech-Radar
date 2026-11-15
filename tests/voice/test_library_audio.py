from __future__ import annotations

from techradar.voice.library_audio import (
    SlideText,
    chapters_by_time,
    offset_words,
)
from techradar.voice.transcribe import Word


def words_over(duration_s: float) -> list[Word]:
    words: list[Word] = []
    t = 0.0
    while t < duration_s:
        words.append(Word(text="word", start=t, end=t + 0.5, prob=0.9))
        t += 1.0
    return words


def test_offset_words() -> None:
    assert offset_words([Word(text="a", start=1.0, end=1.5, prob=0.9)], 600)[0].start == 601.0


def test_chapters_by_time_titles_and_slides() -> None:
    chs = chapters_by_time(words_over(1800), [SlideText(ts_s=30, text="Deadlocks")])
    assert [c.title for c in chs] == [
        "Part 1 (00:00–15:00)",
        "Part 2 (15:00–30:00)",
    ]
    assert "> Slide: Deadlocks" in chs[0].text
