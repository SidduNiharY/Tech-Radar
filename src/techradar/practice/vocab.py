# Owner: spaCy, wordfreq and the en_core_web_sm model are not approved dependencies. The pure
# Python DefaultWordAnalyzer below stands in behind the WordAnalyzer Protocol; a server that
# approves them injects a spaCy/wordfreq analyzer (job: worker/tasks.py `vocab_job`).
from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Annotated, Protocol

from pydantic import AfterValidator, BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import Chunk
from techradar.db.models import Flashcard as DBFlashcard
from techradar.db.models import Vocab as DBVocab
from techradar.llm.client import Completer, complete_json
from techradar.llm.roles import Role
from techradar.practice.flashcards import new_card_state
from techradar.security.text import sanitize_text
from techradar.security.untrusted import wrap_untrusted

logger = logging.getLogger(__name__)

_LINK_RE = re.compile(r"(?i)(https?://|www\.|\]\(|!\[|<\s*(a|img|script|iframe)\b|data:)")


def _contains_link(text: str) -> bool:
    """Returns True if the text contains URLs or link markdown/HTML patterns."""
    return bool(_LINK_RE.search(text))


def reject_links(value: str) -> str:
    """Rejects strings that contain link markdown, HTML or URLs (SEC-20)."""
    if _LINK_RE.search(value):
        raise ValueError("links are not allowed")
    return value


NoLinks = Annotated[str, AfterValidator(reject_links)]


class WordAnalyzer(Protocol):
    """Protocol for NLP lemmatization, POS tagging, and frequency analysis (Section 9)."""

    def zipf_frequency(self, word: str) -> float: ...
    def lemmatize(self, word: str) -> str: ...
    def is_proper_noun(self, word: str, sentence: str) -> bool: ...


class DefaultWordAnalyzer:
    """Pure-Python default analyzer with regex tokenization and stopword heuristics."""

    _KNOWN_PROPER_NOUNS: frozenset[str] = frozenset(
        {
            "delhi",
            "mumbai",
            "kolkata",
            "chennai",
            "bengaluru",
            "hyderabad",
            "ahmedabad",
            "pune",
            "varanasi",
            "india",
            "bharat",
            "asia",
            "europe",
            "america",
            "africa",
            "london",
            "paris",
            "tokyo",
            "beijing",
            "washington",
            "new york",
            "russia",
            "china",
            "modi",
            "gandhi",
            "nehru",
            "rahul",
            "priya",
            "amit",
            "sharma",
            "patel",
        }
    )

    _COMMON_WORDS: frozenset[str] = frozenset(
        {
            "the",
            "be",
            "to",
            "of",
            "and",
            "a",
            "in",
            "that",
            "have",
            "i",
            "it",
            "for",
            "not",
            "on",
            "with",
            "he",
            "as",
            "you",
            "do",
            "at",
            "this",
            "but",
            "his",
            "by",
            "from",
            "they",
            "we",
            "say",
            "her",
            "she",
            "or",
            "an",
            "will",
            "my",
            "one",
            "all",
            "would",
            "there",
            "their",
            "what",
            "so",
            "up",
            "out",
            "if",
            "about",
            "who",
            "get",
            "which",
            "go",
            "me",
            "when",
            "make",
            "can",
            "like",
            "time",
            "no",
            "just",
            "him",
            "know",
            "take",
            "people",
            "into",
            "year",
            "your",
            "good",
            "some",
            "could",
            "them",
            "see",
            "other",
            "than",
            "then",
            "now",
            "look",
            "only",
            "come",
            "its",
            "over",
            "think",
            "also",
            "back",
            "after",
            "use",
            "two",
            "how",
            "our",
            "work",
            "first",
            "well",
            "way",
            "even",
            "new",
            "want",
            "because",
            "any",
            "these",
            "give",
            "day",
            "most",
            "us",
            "saw",
            "data",
            "economic",
            "economy",
            "rebound",
            "market",
            "business",
            "government",
            "system",
            "company",
            "state",
            "country",
            "world",
            "national",
            "official",
            "officials",
            "report",
            "growth",
            "price",
            "policy",
            "industry",
            "financial",
            "development",
            "information",
            "public",
            "power",
            "interest",
            "service",
            "security",
            "sector",
            "bank",
            "banks",
            "trade",
            "rate",
            "rates",
            "inflation",
            "money",
            "fund",
            "funds",
            "capital",
            "investment",
            "investor",
            "investors",
            "production",
            "product",
            "products",
            "demand",
            "supply",
            "level",
            "levels",
            "measure",
            "measures",
            "figure",
            "figures",
            "period",
            "number",
            "numbers",
            "percent",
            "percentage",
            "million",
            "billion",
            "action",
            "activity",
            "activities",
            "board",
            "center",
            "change",
            "changes",
            "court",
            "decision",
            "effort",
            "efforts",
            "group",
            "groups",
            "issue",
            "issues",
            "member",
            "members",
            "minister",
            "office",
            "party",
            "president",
            "process",
            "result",
            "results",
            "union",
            "value",
            "values",
            "water",
            "order",
            "study",
            "studies",
            "research",
            "labor",
            "labour",
            "health",
            "energy",
            "force",
            "forces",
            "source",
            "sources",
            "resource",
            "resources",
            "school",
            "student",
            "students",
            "teacher",
            "teachers",
            "university",
            "college",
            "test",
            "exam",
            "paper",
            "book",
            "page",
            "news",
            "story",
            "stories",
            "city",
            "town",
            "place",
            "house",
            "home",
            "building",
            "road",
            "street",
            "car",
            "train",
            "flight",
            "air",
            "land",
            "area",
            "region",
            "district",
            "village",
            "point",
            "case",
            "fact",
            "week",
            "month",
            "history",
            "culture",
            "society",
            "view",
            "hand",
            "part",
            "side",
            "head",
            "eye",
            "face",
            "line",
            "end",
            "name",
            "word",
            "idea",
            "right",
            "left",
            "high",
            "low",
            "long",
            "short",
            "large",
            "small",
            "great",
            "little",
            "young",
            "old",
            "early",
            "late",
            "important",
            "major",
            "social",
            "general",
            "special",
            "real",
            "clear",
            "open",
            "free",
            "strong",
            "full",
            "easy",
            "hard",
            "simple",
            "common",
            "certain",
            "different",
            "similar",
            "possible",
            "whole",
            "recent",
            "true",
            "able",
            "available",
            "likely",
            "present",
            "main",
            "particular",
            "said",
            "made",
            "went",
            "gone",
            "knew",
            "known",
            "took",
            "taken",
            "came",
            "thought",
            "looked",
            "wanted",
            "gave",
            "given",
            "used",
            "found",
            "told",
            "asked",
            "worked",
            "seemed",
            "felt",
            "tried",
            "called",
            "needed",
            "helped",
            "showed",
            "shown",
            "played",
            "moved",
            "lived",
            "believed",
            "brought",
            "happened",
            "written",
            "wrote",
            "read",
            "became",
            "become",
            "held",
            "hold",
            "ran",
            "run",
            "stood",
            "stand",
            "lost",
            "lose",
            "paid",
            "pay",
            "met",
            "meet",
            "included",
            "include",
            "set",
            "led",
            "lead",
            "understood",
            "understand",
            "watched",
            "watch",
            "followed",
            "follow",
            "stopped",
            "stop",
            "created",
            "create",
            "speak",
            "spoke",
            "spoken",
            "allow",
            "allowed",
            "add",
            "added",
            "spend",
            "spent",
            "grow",
            "grew",
            "grown",
            "opened",
            "walk",
            "walked",
            "win",
            "won",
            "offer",
            "offered",
            "remember",
            "remembered",
            "love",
            "loved",
            "consider",
            "considered",
            "appear",
            "appeared",
            "buy",
            "bought",
            "wait",
            "waited",
            "serve",
            "served",
            "die",
            "died",
            "send",
            "sent",
            "expect",
            "expected",
            "build",
            "built",
            "stay",
            "stayed",
            "fall",
            "fell",
            "fallen",
            "cut",
            "reach",
            "reached",
            "kill",
            "killed",
            "remain",
            "remained",
        }
    )

    def split_sentences(self, text: str) -> list[str]:
        """Split text into sentences while keeping punctuation attached verbatim."""
        raw = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]
        return raw if raw else ([text.strip()] if text.strip() else [])

    def lemmatize(self, word: str) -> str:
        """Heuristic English lemmatizer stripping regular inflections."""
        w = word.lower()
        if w.endswith("ies") and len(w) > 4:
            return w[:-3] + "y"
        if w.endswith("es") and len(w) > 4:
            for suffix in ("ches", "shes", "sses", "xes", "zes"):
                if w.endswith(suffix):
                    return w[:-2]
            if w.endswith("ves") and len(w) > 4:
                return w[:-3] + "f"
            return w[:-1]
        if w.endswith("s") and not w.endswith("ss") and len(w) > 3:
            return w[:-1]
        if w.endswith("ied") and len(w) > 4:
            return w[:-3] + "y"
        if w.endswith("ed") and len(w) > 4:
            if w.endswith("eed"):
                return w
            if len(w) > 5 and w[-3] == w[-4] and w[-3] in "bcdfghjklmnpqrstvwxyz":
                return w[:-3]
            return w[:-2] if not w.endswith("e") else w[:-1]
        if w.endswith("ing") and len(w) > 5:
            if len(w) > 6 and w[-4] == w[-5] and w[-4] in "bcdfghjklmnpqrstvwxyz":
                return w[:-4]
            return w[:-3]
        return w

    def is_proper_noun(self, word: str, sentence: str) -> bool:
        """Determines if a word token represents a proper noun."""
        if not word or not word[0].isupper():
            return False
        w_lower = word.lower()
        if w_lower in self._KNOWN_PROPER_NOUNS:
            return True

        # Check position in sentence
        idx = sentence.find(word)
        is_sentence_start = idx <= 0 or not any(c.isalnum() for c in sentence[:idx])
        if not is_sentence_start:
            # Capitalized word within sentence is a proper noun
            return True

        # At sentence start: if lowercase lemma is a common English word, it's not proper
        lemma = self.lemmatize(w_lower)
        if lemma in self._COMMON_WORDS or w_lower in self._COMMON_WORDS:
            return False

        # Otherwise, capitalized word not in common lexicon is treated as proper noun
        return True

    def zipf_frequency(self, word: str) -> float:
        """Estimated Zipf frequency scale (0.0 to 7.0). Common words >= 3.5, rare words < 3.5."""
        w = word.lower()
        lemma = self.lemmatize(w)
        if lemma in self._COMMON_WORDS or w in self._COMMON_WORDS:
            return 4.5
        return 2.5


def candidate_words(
    text: str,
    *,
    max_zipf: float = 3.5,
    min_len: int = 5,
    analyzer: WordAnalyzer | None = None,
) -> list[tuple[str, str]]:
    """Extracts candidate vocabulary words from text as (lemma, verbatim_sentence) pairs.

    Skips proper nouns and common words (Zipf >= max_zipf). De-duplicated by lemma.
    """
    proc = analyzer if analyzer is not None else DefaultWordAnalyzer()
    if hasattr(proc, "split_sentences") and callable(proc.split_sentences):
        sentences = proc.split_sentences(text)
    else:
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]

    seen_lemmas: set[str] = set()
    results: list[tuple[str, str]] = []

    for sentence in sentences:
        if not sentence:
            continue
        # Extract word tokens with word boundaries
        tokens = re.findall(r"\b[A-Za-z]+(?:'[A-Za-z]+)?\b", sentence)
        for token in tokens:
            if proc.is_proper_noun(token, sentence):
                continue
            lemma = proc.lemmatize(token)
            if len(lemma) < min_len:
                continue
            if proc.zipf_frequency(lemma) >= max_zipf:
                continue
            if lemma.lower() in seen_lemmas:
                continue

            seen_lemmas.add(lemma.lower())
            results.append((lemma, sentence))

    return results


class VocabMeaning(BaseModel):
    """Pydantic model for dictionary definition and word relationships."""

    meaning: Annotated[
        str,
        Field(max_length=160),
        AfterValidator(reject_links),
    ]
    synonyms: list[
        Annotated[
            str,
            Field(max_length=60),
            AfterValidator(reject_links),
        ]
    ] = Field(default_factory=list)
    antonyms: list[
        Annotated[
            str,
            Field(max_length=60),
            AfterValidator(reject_links),
        ]
    ] = Field(default_factory=list)

    @field_validator("meaning")
    @classmethod
    def validate_meaning(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("meaning cannot be empty")
        return v

    @field_validator("synonyms", "antonyms")
    @classmethod
    def validate_word_lists(cls, v: list[str]) -> list[str]:
        cleaned = [item.strip() for item in v if item.strip()]
        return cleaned[:3]


class VocabResult(BaseModel):
    """Result of running daily vocabulary job."""

    items_created: int = 0
    words: list[str] = Field(default_factory=list)
    skipped_reason: str | None = None


async def run_vocab(
    session: AsyncSession,
    completer: Completer,
    *,
    now: datetime,
    limit: int = 5,
    analyzer: WordAnalyzer | None = None,
    corpus: Sequence[str] | None = None,
) -> VocabResult:
    """Body of vocab_job: extracts candidates, generates definitions, and stores cards."""
    text_sources: list[str] = []
    if corpus:
        text_sources.extend(corpus)
    else:
        since = now - timedelta(days=1)
        stmt = (
            select(Chunk.text)
            .where(Chunk.lang == "en", Chunk.flagged.is_(False), Chunk.indexed_at >= since)
            .order_by(Chunk.id.desc())
            .limit(20)
        )
        text_sources.extend((await session.execute(stmt)).scalars().all())

    combined_text = "\n\n".join(text_sources)
    candidates = candidate_words(combined_text, analyzer=analyzer) if combined_text else []

    existing_words = {
        w.lower() for w in (await session.execute(select(DBVocab.word))).scalars().all()
    }

    new_candidates = [(w, s) for w, s in candidates if w.lower() not in existing_words]
    if not new_candidates:
        return VocabResult(
            items_created=0,
            words=[],
            skipped_reason="no_candidates",
        )

    created_words: list[str] = []
    system_prompt = (
        "You are an English vocabulary tutor. Provide a concise definition (≤160 characters), "
        "up to 3 synonyms, and up to 3 antonyms for the target word in its sentence context. "
        "Do not include any URLs or links."
    )

    for word, sentence in new_candidates[:limit]:
        user_prompt = f"Word: {word}\nSentence context:\n{wrap_untrusted(sanitize_text(sentence))}"
        try:
            meaning_obj = await complete_json(
                completer,
                Role.WORKER,
                system_prompt,
                user_prompt,
                VocabMeaning,
                attempts=1,
            )
        except Exception as exc:
            logger.debug("Failed to generate meaning for word %s: %s", word, exc)
            continue

        vocab_row = DBVocab(
            word=word,
            sentence=sentence,
            meaning=meaning_obj.meaning,
            synonyms=meaning_obj.synonyms,
            antonyms=meaning_obj.antonyms,
            created_at=now,
        )
        session.add(vocab_row)
        await session.flush()

        synonyms_str = ", ".join(meaning_obj.synonyms) if meaning_obj.synonyms else "None"
        antonyms_str = ", ".join(meaning_obj.antonyms) if meaning_obj.antonyms else "None"
        back_text = (
            f"{meaning_obj.meaning}\n\n"
            f"Synonyms: {synonyms_str}\n"
            f"Antonyms: {antonyms_str}\n\n"
            f"(AI meaning)"
        )
        card_state, card_due = new_card_state(now)
        card_row = DBFlashcard(
            front=f"{word}\n\nContext: {sentence}",
            back=back_text,
            source_kind="vocab",
            source_id=vocab_row.id,
            fsrs_card=card_state,
            due=card_due,
        )
        session.add(card_row)
        created_words.append(word)

    if created_words:
        await session.flush()

    return VocabResult(
        items_created=len(created_words),
        words=created_words,
        skipped_reason=None if created_words else "generation_failed",
    )
