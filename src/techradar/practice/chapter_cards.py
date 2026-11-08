from __future__ import annotations

import re
from typing import Any

from techradar.practice.fsrs import Card, State


class ChapterCard(Card):
    """Spaced repetition flashcard generated from a chapter chunk."""

    card_key: str
    front: str = ""
    back: str = ""
    chapter_slug: str = ""

    @property
    def key(self) -> str:
        return self.card_key

    def __getitem__(self, item: str) -> Any:
        return getattr(self, item)


def _is_chunk_flagged(chunk: Any) -> bool:
    """Returns True if chunk is flagged by intake gateway."""
    if isinstance(chunk, str):
        lower = chunk.strip().lower()
        return lower.startswith("[flagged]") or lower.startswith("flagged:")
    if hasattr(chunk, "flagged"):
        return bool(chunk.flagged)
    if isinstance(chunk, dict):
        return bool(chunk.get("flagged", False))
    return False


def _extract_chunk_text(chunk: Any) -> str:
    """Extracts raw text content from a chunk item."""
    if isinstance(chunk, str):
        return chunk
    if hasattr(chunk, "text"):
        return str(chunk.text)
    if isinstance(chunk, dict) and "text" in chunk:
        return str(chunk["text"])
    return str(chunk)


class _GenerateCardsDescriptor:
    """Hybrid descriptor allowing generate_cards to be called on class or instance."""

    def __get__(self, instance: Any, owner: Any = None) -> Any:
        def _wrapper(
            chapter_slug: str,
            chunks: list[str] | list[Any],
            existing_card_keys: set[str] | None = None,
        ) -> list[Card]:
            min_c = getattr(
                instance,
                "min_cards",
                getattr(owner, "DEFAULT_MIN_CARDS", 10),
            )
            max_c = getattr(
                instance,
                "max_cards",
                getattr(owner, "DEFAULT_MAX_CARDS", 20),
            )
            return ChapterCardsGenerator._generate_cards_impl(
                chapter_slug=chapter_slug,
                chunks=chunks,
                existing_card_keys=existing_card_keys,
                min_cards=min_c,
                max_cards=max_c,
            )

        return _wrapper


class ChapterCardsGenerator:
    """Generates FSRS flashcards from unflagged reading chunks of a chapter."""

    DEFAULT_MIN_CARDS = 10
    DEFAULT_MAX_CARDS = 20

    def __init__(
        self,
        min_cards: int = DEFAULT_MIN_CARDS,
        max_cards: int = DEFAULT_MAX_CARDS,
    ) -> None:
        self.min_cards = min_cards
        self.max_cards = max_cards

    generate_cards = _GenerateCardsDescriptor()

    @staticmethod
    def _generate_cards_impl(
        chapter_slug: str,
        chunks: list[str] | list[Any],
        existing_card_keys: set[str] | None = None,
        min_cards: int = DEFAULT_MIN_CARDS,
        max_cards: int = DEFAULT_MAX_CARDS,
    ) -> list[Card]:
        if not chunks:
            return []

        # Filter out flagged chunks (SEC-57)
        unflagged_chunks = [c for c in chunks if not _is_chunk_flagged(c)]
        if not unflagged_chunks:
            return []

        # Extract text statements/facts
        sentences: list[str] = []
        for chunk in unflagged_chunks:
            text = _extract_chunk_text(chunk).strip()
            if not text:
                continue
            parts = re.split(r"[.\n;]+", text)
            for part in parts:
                cleaned = part.strip()
                if len(cleaned) >= 5:
                    sentences.append(cleaned)

        if not sentences:
            # Fallback to non-empty chunk texts if no sentence split found
            sentences = [
                _extract_chunk_text(c).strip()
                for c in unflagged_chunks
                if _extract_chunk_text(c).strip()
            ]

        if not sentences:
            return []

        target_count = min(max(len(sentences), min_cards), max_cards)
        existing = existing_card_keys or set()

        cards: list[Card] = []
        for i in range(target_count):
            card_key = f"{chapter_slug}:card_{i}"

            # Idempotency check: skip already existing card keys
            if (
                card_key in existing
                or f"{chapter_slug}:{i}" in existing
                or f"{chapter_slug}:card_{i:02d}" in existing
            ):
                continue

            sentence = sentences[i % len(sentences)]
            prompt = sentence if len(sentence) <= 80 else f"{sentence[:77]}..."

            card = ChapterCard(
                card_key=card_key,
                front=f"[{chapter_slug}] Key Concept #{i + 1}: {prompt}",
                back=f"Detail: {sentence}",
                chapter_slug=chapter_slug,
                state=State.NEW,
            )
            cards.append(card)

        return cards
