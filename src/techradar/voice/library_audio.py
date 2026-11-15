from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict

from techradar.voice.transcribe import Word


def offset_words(words: Sequence[Word], offset_s: float) -> list[Word]:
    """Shift timestamps of a sequence of words by offset_s seconds."""
    return [
        Word(
            text=w.text,
            start=round(w.start + offset_s, 3),
            end=round(w.end + offset_s, 3),
            prob=w.prob,
        )
        for w in words
    ]


class SlideText(BaseModel):
    model_config = ConfigDict(frozen=True)

    ts_s: float
    text: str


class TimedChapter(BaseModel):
    model_config = ConfigDict(frozen=True)

    ordinal: int
    title: str
    ts_start: float
    ts_end: float
    text: str


def _format_time(seconds: float) -> str:
    m = int(seconds) // 60
    s = int(seconds) % 60
    return f"{m:02d}:{s:02d}"


def chapters_by_time(
    words: Sequence[Word],
    slides: Sequence[SlideText],
    every_s: int = 900,
) -> list[TimedChapter]:
    """Segment words and visual slide OCR into timed chapters."""
    if not words and not slides:
        return []

    max_ts = 0.0
    if words:
        max_ts = max(max_ts, max(w.end for w in words))
    if slides:
        max_ts = max(max_ts, max(s.ts_s for s in slides))

    total_duration = max(max_ts, float(every_s))
    num_parts = max(1, int((total_duration + every_s - 1) // every_s))

    chapters: list[TimedChapter] = []

    for i in range(num_parts):
        part_num = i + 1
        t_start = float(i * every_s)
        t_end = float((i + 1) * every_s)

        title = f"Part {part_num} ({_format_time(t_start)}–{_format_time(t_end)})"

        # Collect items in this window
        part_slides = [s for s in slides if t_start <= s.ts_s < t_end]
        part_words = [w for w in words if t_start <= w.start < t_end]

        lines: list[str] = []

        # Interleave slides and words chronologically
        events: list[tuple[float, str]] = []
        for s in part_slides:
            events.append((s.ts_s, f"<!-- t {int(s.ts_s)} -->\n> Slide: {s.text}"))

        if part_words:
            # Group words by approx 10-second segments or sentences
            current_words: list[str] = []
            current_start = part_words[0].start
            for w in part_words:
                if not current_words:
                    current_start = w.start
                current_words.append(w.text)
                if len(current_words) >= 20 or w.text.endswith((".", "?", "!")):
                    line_text = " ".join(current_words)
                    events.append(
                        (
                            current_start,
                            f"<!-- t {int(current_start)} -->\n{line_text}",
                        )
                    )
                    current_words = []
            if current_words:
                events.append(
                    (
                        current_start,
                        f"<!-- t {int(current_start)} -->\n{' '.join(current_words)}",
                    )
                )

        events.sort(key=lambda x: x[0])
        lines = [ev[1] for ev in events]
        chapter_text = "\n\n".join(lines) if lines else f"<!-- t {int(t_start)} -->"

        chapters.append(
            TimedChapter(
                ordinal=part_num,
                title=title,
                ts_start=t_start,
                ts_end=t_end,
                text=chapter_text,
            )
        )

    return chapters
