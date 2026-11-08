from __future__ import annotations

import re
from collections.abc import Iterator, Sequence
from datetime import UTC, datetime

from pydantic import BaseModel, Field

from techradar.practice.fsrs import Card, Rating, schedule_card

_LINK_RE = re.compile(r"(?i)(https?://|www\.|\]\(|!\[|<\s*(a|img|script|iframe)\b|data:)")


def _contains_link(text: str) -> bool:
    """Returns True if the text contains URLs or link markdown/HTML patterns."""
    return bool(_LINK_RE.search(text))


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
            # Separate due items and new items
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

            # Sort due items oldest due first
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
