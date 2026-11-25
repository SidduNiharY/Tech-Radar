"""Learner topic mastery level computation and prompt guidance."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from typing import Any, Literal

Level = Literal["new", "learning", "exam_ready", "mastered"]


def mastery_level(
    quiz_accuracy: float | None,
    stability_days: float | None,
    reviews: int,
) -> Level:
    """Compute mastery tier based on quiz performance and FSRS card stability."""
    if quiz_accuracy is None and reviews < 3:
        return "new"

    if (
        quiz_accuracy is not None
        and quiz_accuracy >= 0.90
        and stability_days is not None
        and stability_days >= 60.0
    ):
        return "mastered"

    if (
        quiz_accuracy is not None
        and quiz_accuracy >= 0.80
        and stability_days is not None
        and stability_days >= 21.0
    ):
        return "exam_ready"

    return "learning"


KNOWN_TOPICS_LINE = (
    "I already know some topics in this question well, so skip their basics. "
    "The topics are listed in the question between the UNTRUSTED markers."
)


def clean_topic(topic: str) -> str:
    """A topic name on one line without control or invisible characters, cut to 120.

    Topic names come from book and chapter titles, which come from files: untrusted text.
    """
    from techradar.security.text import sanitize_text

    return " ".join(sanitize_text(topic).split())[:120]


def mastered_topics(levels: Mapping[str, Level], topics_in_question: Sequence[str]) -> list[str]:
    """The cleaned names of the mastered topics the question is about (data, never a prompt)."""
    names = [clean_topic(t) for t in topics_in_question if levels.get(t) == "mastered"]
    return [n for n in names if n]


def mastery_line(
    levels: Mapping[str, Level],
    topics_in_question: Sequence[str],
) -> str | None:
    """A fixed system-prompt line, or None. It never contains a topic name (SEC-17, SEC-48).

    The names go in the user prompt between UNTRUSTED markers (see `rag.answer`).
    """
    return KNOWN_TOPICS_LINE if mastered_topics(levels, topics_in_question) else None


# --- Phase 11 Task 7: the nightly mastery job -----------------------------------------------

MASTERY_WINDOW_DAYS = 90


async def compute_mastery(session: Any, now: datetime) -> int:
    """Recompute the level of every chapter that has quiz answers or reviewed cards.

    A topic is `<book title> · <chapter title>`. Accuracy is the share of correct quiz answers
    in 90 days; stability is the mean FSRS stability of the chapter's reviewed cards. Returns
    how many topics were written. Plain code only (SEC-48).
    """
    from sqlalchemy import select

    from techradar.db.models import (
        MCQ,
        Flashcard,
        LibraryChapter,
        LibraryDoc,
        QuizAttempt,
        TopicMastery,
    )

    since = now - timedelta(days=MASTERY_WINDOW_DAYS)
    attempts: dict[int, list[bool]] = {}
    rows = await session.execute(
        select(MCQ.chapter_id, QuizAttempt.correct)
        .join(QuizAttempt, QuizAttempt.mcq_id == MCQ.id)
        .where(MCQ.chapter_id.is_not(None), QuizAttempt.answered_at >= since)
    )
    for chapter_id, correct in rows.all():
        attempts.setdefault(chapter_id, []).append(bool(correct))
    cards: dict[int, list[dict[str, Any]]] = {}
    card_rows = await session.execute(
        select(Flashcard.source_id, Flashcard.fsrs_card).where(
            Flashcard.source_kind == "chapter",
            Flashcard.source_id.is_not(None),
            Flashcard.retired.is_(False),
        )
    )
    for source_id, fsrs in card_rows.all():
        cards.setdefault(source_id, []).append(fsrs or {})

    written = 0
    for chapter_id in sorted(set(attempts) | set(cards)):
        chapter = await session.get(LibraryChapter, chapter_id)
        if chapter is None:
            continue
        doc = await session.get(LibraryDoc, chapter.doc_id)
        topic = f"{doc.title if doc else 'book'} · {chapter.title}"[:200]
        tries = attempts.get(chapter_id, [])
        accuracy = sum(tries) / len(tries) if tries else None
        reviewed = [c for c in cards.get(chapter_id, []) if int(c.get("reps", 0) or 0) > 0]
        stability = (
            sum(float(c.get("stability", 0.0) or 0.0) for c in reviewed) / len(reviewed)
            if reviewed
            else None
        )
        reviews = sum(int(c.get("reps", 0) or 0) for c in reviewed) + len(tries)
        level = mastery_level(accuracy, stability, reviews)
        row = await session.get(TopicMastery, topic)
        if row is None:
            session.add(
                TopicMastery(
                    topic=topic,
                    level=level,
                    quiz_accuracy=accuracy,
                    stability_days=stability,
                    reviews=reviews,
                    prev_level=None,
                    updated_at=now,
                )
            )
        else:
            row.prev_level = row.level if row.level != level else row.prev_level
            row.level, row.quiz_accuracy = level, accuracy
            row.stability_days, row.reviews, row.updated_at = stability, reviews, now
        written += 1
    await session.flush()
    return written


async def load_levels(session: Any) -> dict[str, Level]:
    """Every stored topic level."""
    from sqlalchemy import select

    from techradar.db.models import TopicMastery

    rows = (await session.execute(select(TopicMastery.topic, TopicMastery.level))).all()
    return {t: lv for t, lv in rows}


def topics_in_question(question: str, levels: Mapping[str, Level]) -> list[str]:
    """Stored topics whose chapter title the question names."""
    low = question.lower()
    found: list[str] = []
    for topic in levels:
        chapter = topic.split(" · ")[-1].strip().lower()
        if len(chapter) >= 4 and chapter in low:
            found.append(topic)
    return found
