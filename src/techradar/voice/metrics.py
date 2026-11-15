from __future__ import annotations

import re
from collections import Counter

from pydantic import BaseModel, ConfigDict

from techradar.voice.transcribe import Transcript

FILLERS: tuple[str, ...] = (
    "um",
    "uh",
    "er",
    "ah",
    "hmm",
    "basically",
    "actually",
    "you know",
    "i mean",
)

STOPWORDS: frozenset[str] = frozenset(
    {
        "a",
        "about",
        "all",
        "also",
        "and",
        "as",
        "at",
        "be",
        "because",
        "but",
        "by",
        "can",
        "come",
        "could",
        "day",
        "do",
        "even",
        "find",
        "first",
        "for",
        "from",
        "get",
        "give",
        "go",
        "have",
        "he",
        "her",
        "here",
        "him",
        "his",
        "how",
        "i",
        "if",
        "in",
        "into",
        "it",
        "its",
        "just",
        "know",
        "like",
        "look",
        "make",
        "man",
        "many",
        "me",
        "more",
        "my",
        "new",
        "no",
        "not",
        "now",
        "of",
        "on",
        "one",
        "only",
        "or",
        "other",
        "our",
        "out",
        "people",
        "say",
        "see",
        "she",
        "so",
        "some",
        "take",
        "tell",
        "than",
        "that",
        "the",
        "their",
        "them",
        "then",
        "there",
        "these",
        "they",
        "thing",
        "think",
        "this",
        "those",
        "time",
        "to",
        "two",
        "up",
        "use",
        "very",
        "want",
        "way",
        "we",
        "well",
        "what",
        "when",
        "which",
        "who",
        "will",
        "with",
        "would",
        "year",
        "you",
        "your",
    }
)


class SpeechMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    words_per_min: float
    filler_count: int
    fillers_per_min: float
    filler_breakdown: dict[str, int]
    long_pauses: int
    avg_sentence_words: float
    type_token_ratio: float
    overused: list[tuple[str, int]]


def compute_metrics(t: Transcript) -> SpeechMetrics:
    """Computes speech fluency and vocabulary metrics from transcript."""
    words = t.words
    duration = max(t.duration_s, 0.001)

    # Detect multi-word and single-word fillers
    filler_counts: dict[str, int] = {}
    filler_word_indices: set[int] = set()

    # Normalize word tokens
    clean_words = [re.sub(r"[^\w']", "", w.text).lower() for w in words]

    # Check 2-word fillers: "you know", "i mean"
    for i in range(len(clean_words) - 1):
        pair = f"{clean_words[i]} {clean_words[i + 1]}"
        if pair in ("you know", "i mean"):
            filler_counts[pair] = filler_counts.get(pair, 0) + 1
            filler_word_indices.add(i)
            filler_word_indices.add(i + 1)

    # Check single-word fillers
    single_fillers = {"um", "uh", "er", "ah", "hmm", "basically", "actually"}
    for i, cw in enumerate(clean_words):
        if i in filler_word_indices:
            continue
        if cw in single_fillers:
            filler_counts[cw] = filler_counts.get(cw, 0) + 1
            filler_word_indices.add(i)
        elif cw == "like":
            is_like_filler = False
            # Check text punctuation "like,"
            if "like," in words[i].text.lower():
                is_like_filler = True
            elif i + 1 < len(words):
                gap = words[i + 1].start - words[i].end
                if gap >= 0.3:
                    is_like_filler = True
            elif i == len(words) - 1 and duration - words[i].end >= 0.3:
                is_like_filler = True

            if is_like_filler:
                filler_counts["like"] = filler_counts.get("like", 0) + 1
                filler_word_indices.add(i)

    # Filter out filler words for vocabulary and WPM calculation
    non_filler_tokens: list[str] = []
    for i, cw in enumerate(clean_words):
        if i not in filler_word_indices and cw:
            non_filler_tokens.append(cw)

    # Words per minute
    wpm = round((len(non_filler_tokens) / duration) * 60.0, 1) if duration > 0 else 0.0

    # Fillers per minute
    total_fillers = sum(filler_counts.values())
    fpm = round((total_fillers / duration) * 60.0, 1) if duration > 0 else 0.0

    # Long pauses (> 1.0s gap between words)
    long_pauses = 0
    for i in range(len(words) - 1):
        gap = words[i + 1].start - words[i].end
        if gap > 1.0:
            long_pauses += 1

    # Type-token ratio
    ttr = (
        round(len(set(non_filler_tokens)) / len(non_filler_tokens), 2) if non_filler_tokens else 0.0
    )

    # Average sentence words
    sentences = [s.strip() for s in re.split(r"[.!?]+", t.text) if s.strip()]
    if sentences:
        total_sw = sum(len(s.split()) for s in sentences)
        avg_sentence_words = round(total_sw / len(sentences), 1)
    else:
        avg_sentence_words = float(len(non_filler_tokens))

    # Overused words: non-stopwords used >= 5 times, top 3
    counts = Counter(non_filler_tokens)
    overused = [
        (w, count) for w, count in counts.most_common() if count >= 5 and w not in STOPWORDS
    ][:3]

    return SpeechMetrics(
        words_per_min=wpm,
        filler_count=total_fillers,
        fillers_per_min=fpm,
        filler_breakdown=filler_counts,
        long_pauses=long_pauses,
        avg_sentence_words=avg_sentence_words,
        type_token_ratio=ttr,
        overused=overused,
    )
