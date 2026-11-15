# WIRING(claude): needs spacy, wordfreq (not approved) behind WordAnalyzer protocol
# WIRING(claude): worker/tasks.py needs grammar_job and vocab_job
from __future__ import annotations

import logging
import re
from collections.abc import Iterator, Sequence
from datetime import UTC, datetime, timedelta
from typing import Annotated, Protocol

from pydantic import AfterValidator, BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import Flashcard as DBFlashcard
from techradar.db.models import Vocab as DBVocab
from techradar.llm.client import Completer, complete_json
from techradar.llm.roles import Role
from techradar.practice.fsrs import Card, Rating, schedule_card

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
        try:
            from techradar.db.models import Chunk

            stmt = (
                select(Chunk.text)
                .where(
                    Chunk.lang == "en",
                    Chunk.flagged.is_(False),
                    Chunk.indexed_at >= now - timedelta(days=1),
                )
                .order_by(Chunk.id.desc())
                .limit(20)
            )
            res = await session.execute(stmt)
            chunks = list(res.scalars().all())
            if chunks:
                text_sources.extend(chunks)
            else:
                stmt_fb = (
                    select(Chunk.text)
                    .where(Chunk.lang == "en", Chunk.flagged.is_(False))
                    .order_by(Chunk.id.desc())
                    .limit(20)
                )
                res_fb = await session.execute(stmt_fb)
                text_sources.extend(res_fb.scalars().all())
        except Exception as exc:
            logger.debug("Failed to query chunks for vocabulary candidates: %s", exc)

    combined_text = "\n\n".join(text_sources)
    candidates = candidate_words(combined_text, analyzer=analyzer) if combined_text else []

    existing_words: set[str] = set()
    try:
        res_existing = await session.execute(select(DBVocab.word))
        existing_words = {w.lower() for w in res_existing.scalars().all()}
    except Exception as exc:
        logger.debug("Failed to query existing vocab: %s", exc)

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
        user_prompt = f"Word: {word}\nSentence context: {sentence}"
        try:
            meaning_obj = await complete_json(
                completer,
                Role.WORKER,
                system_prompt,
                user_prompt,
                VocabMeaning,
                attempts=1,
            )
        except IndexError, StopIteration:
            break
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
        card_row = DBFlashcard(
            front=f"{word}\n\nContext: {sentence}",
            back=back_text,
            source_kind="vocab",
            source_id=vocab_row.id,
            fsrs_card={},
            due=now,
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


# ---------------------------------------------------------------------------
# Backward Compatibility for VocabItem and VocabDailyDeck
# ---------------------------------------------------------------------------


class VocabItem(BaseModel):
    word: str
    pos: str
    definition: str
    synonyms: list[str] = Field(default_factory=list)
    antonyms: list[str] = Field(default_factory=list)
    example_sentence: str
    source_context: str | None = None

    def is_valid(self) -> bool:
        return validate_vocab_item(self)


def validate_vocab_item(item: VocabItem) -> bool:
    """Validates that a vocab item has valid, non-empty text fields and no links (SEC-20)."""
    if not item.word or not item.word.strip():
        return False
    if not item.pos or not item.pos.strip():
        return False
    if not item.definition or not item.definition.strip():
        return False
    if not item.example_sentence or not item.example_sentence.strip():
        return False
    if _contains_link(item.word) or _contains_link(item.definition):
        return False
    if _contains_link(item.example_sentence):
        return False
    if item.source_context and _contains_link(item.source_context):
        return False
    return True


_DEFAULT_VOCAB_POOL: list[VocabItem] = [
    VocabItem(
        word="ephemeral",
        pos="adjective",
        definition="Lasting for a very short time; transitory.",
        synonyms=["fleeting", "transient", "momentary"],
        antonyms=["permanent", "eternal", "enduring"],
        example_sentence="Fashions are ephemeral, but classic style endures.",
        source_context="Technology trends can be ephemeral without strong fundamentals.",
    ),
    VocabItem(
        word="obfuscate",
        pos="verb",
        definition="To deliberately make something obscure, unclear, or difficult to understand.",
        synonyms=["cloud", "confuse", "blur"],
        antonyms=["clarify", "illuminate", "simplify"],
        example_sentence="The company tried to obfuscate its losses behind technical jargon.",
        source_context="Never obfuscate error logs in production systems.",
    ),
    VocabItem(
        word="ubiquitous",
        pos="adjective",
        definition="Present, appearing, or found everywhere.",
        synonyms=["omnipresent", "pervasive", "universal"],
        antonyms=["rare", "scarce", "seldom"],
        example_sentence="Smartphones have become ubiquitous in daily life.",
        source_context="Microcontrollers are now ubiquitous in modern automobiles.",
    ),
    VocabItem(
        word="pragmatic",
        pos="adjective",
        definition="Dealing with things sensibly based on practical considerations.",
        synonyms=["practical", "sensible", "down-to-earth"],
        antonyms=["idealistic", "impractical", "dogmatic"],
        example_sentence="The team adopted a pragmatic approach to the refactor.",
        source_context="A pragmatic engineer favors working code over premature abstractions.",
    ),
    VocabItem(
        word="tenacious",
        pos="adjective",
        definition="Tending to keep a firm hold of something; persistent and determined.",
        synonyms=["persistent", "resolute", "steadfast"],
        antonyms=["vacillating", "yielding", "irresolute"],
        example_sentence="Her tenacious pursuit of the bug solved the memory leak.",
        source_context="Tenacious learners succeed in mastering distributed systems.",
    ),
    VocabItem(
        word="paradigm",
        pos="noun",
        definition="A typical example, pattern, or model of something.",
        synonyms=["model", "framework", "standard"],
        antonyms=["anomaly", "deviation"],
        example_sentence="Declarative code represents a distinct paradigm from imperative code.",
        source_context="RAG represents a new paradigm in knowledge grounding.",
    ),
    VocabItem(
        word="resilient",
        pos="adjective",
        definition="Able to withstand or recover quickly from difficult conditions.",
        synonyms=["tough", "hardy", "robust"],
        antonyms=["fragile", "brittle", "vulnerable"],
        example_sentence="The network architecture proved resilient during the node failover.",
        source_context="Building resilient cloud services requires graceful degradation.",
    ),
    VocabItem(
        word="lucid",
        pos="adjective",
        definition="Expressed clearly; easy to understand.",
        synonyms=["clear", "coherent", "articulate"],
        antonyms=["confusing", "ambiguous", "obscure"],
        example_sentence="The documentation gave a lucid explanation of the protocol.",
        source_context="Write lucid commit messages that explain the rationale.",
    ),
]


class VocabDailyDeck:
    """Manages daily 5-item vocabulary batches and integrates with the FSRS rating loop."""

    def __init__(
        self,
        items: Sequence[VocabItem] | None = None,
        cards: dict[str, Card] | None = None,
    ) -> None:
        self.items: list[VocabItem] = (
            list(items) if items is not None else list(_DEFAULT_VOCAB_POOL)
        )
        self.cards: dict[str, Card] = dict(cards) if cards is not None else {}

        # Ensure all items have an associated card
        for item in self.items:
            if item.word not in self.cards:
                self.cards[item.word] = Card()

    def get_daily_batch(
        self,
        limit: int = 5,
        now: datetime | None = None,
    ) -> list[VocabItem]:
        """Returns a daily batch of up to `limit` (default 5) vocabulary items.

        Prioritizes due review items if `now` is specified, followed by new items.
        """
        valid_items = [it for it in self.items if validate_vocab_item(it)]
        if not valid_items:
            return []

        if now is not None:
            due_items: list[VocabItem] = []
            new_items: list[VocabItem] = []
            other_items: list[VocabItem] = []

            for it in valid_items:
                card = self.get_card(it.word)
                if card.reps == 0:
                    new_items.append(it)
                elif card.due <= now:
                    due_items.append(it)
                else:
                    other_items.append(it)

            due_items.sort(key=lambda it: self.get_card(it.word).due)
            combined = (due_items + new_items + other_items)[:limit]
            return combined

        return valid_items[:limit]

    def daily_batch(self, limit: int = 5) -> list[VocabItem]:
        """Convenience method returning the 5-item daily batch."""
        return self.get_daily_batch(limit=limit)

    def get_card(self, word_or_item: str | VocabItem) -> Card:
        """Retrieves or initializes the FSRS Card for a given word or item."""
        word = word_or_item.word if isinstance(word_or_item, VocabItem) else word_or_item
        if word not in self.cards:
            self.cards[word] = Card()
        return self.cards[word]

    def review(
        self,
        word_or_item: str | VocabItem,
        rating: Rating | int,
        now: datetime | None = None,
    ) -> Card:
        """Reviews a vocabulary item using FSRS scheduling and updates the deck's card."""
        word = word_or_item.word if isinstance(word_or_item, VocabItem) else word_or_item
        card = self.get_card(word)

        if isinstance(rating, int) and not isinstance(rating, Rating):
            rating = Rating(rating)

        current_time = now if now is not None else datetime.now(UTC)
        updated_card = schedule_card(card, rating, current_time)
        self.cards[word] = updated_card
        return updated_card

    def rate(
        self,
        word_or_item: str | VocabItem,
        rating: Rating | int,
        now: datetime | None = None,
    ) -> Card:
        """Alias for review."""
        return self.review(word_or_item, rating, now)

    def __len__(self) -> int:
        return len(self.items)

    def __iter__(self) -> Iterator[VocabItem]:
        return iter(self.items)
